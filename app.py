import os, re, json, time, shutil, threading, random, subprocess, struct
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BASE, "playlists")  # one folder = one playlist
ORDER = "order.txt"  # optional play order (one file name per line)
DATA = os.path.join(BASE, "data.json")
PIFM = os.environ.get("PIFM", os.path.join(BASE, "PiFmRds", "src", "pi_fm_rds"))
FIFO = "/tmp/pifm.ctl"
EXT = (".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus")
os.makedirs(ROOT, exist_ok=True)

D = {"freq": 99.9, "ps": "MaRadio", "shuffle": False, "loop": True,
     "streams": {}, "active": "Main"}
if os.path.exists(DATA):
    D.update(json.load(open(DATA)))
D.pop("playlists", None)


def save():
    json.dump(D, open(DATA, "w"), indent=1)


# ---------- playlists = folders ----------
def safe(name):
    n = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip().strip(".")
    return n or "Playlist"


def plnames():
    return sorted((d for d in os.listdir(ROOT)
                   if os.path.isdir(os.path.join(ROOT, d)) and not d.startswith(".")), key=str.lower)


def fpath(rel):
    p = os.path.normpath(os.path.join(ROOT, rel))
    return p if p.startswith(ROOT + os.sep) else None


def read_pl(name):
    folder = os.path.join(ROOT, name)
    if not os.path.isdir(folder):
        return []
    files = sorted((f for f in os.listdir(folder) if f.lower().endswith(EXT)), key=str.lower)
    order = []
    p = os.path.join(folder, ORDER)
    if os.path.exists(p):
        for l in open(p, encoding="utf-8-sig", errors="ignore"):
            l = l.strip()
            e = "f:%s/%s" % (name, l)
            if l.startswith("s:"):
                order.append(l)
            elif l in files and e not in order:
                order.append(e)
    for f in files:
        e = "f:%s/%s" % (name, f)
        if e not in order:
            order.append(e)
    return order


def playlists():
    return {n: read_pl(n) for n in plnames()}


def write_order(name, tracks):
    lines = []
    for e in tracks:
        if e.startswith("s:"):
            lines.append(e)
        elif e.startswith("f:%s/" % name):
            lines.append(e.split("/", 1)[1])
    with open(os.path.join(ROOT, name, ORDER), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def ensure_default():
    if not plnames():
        os.makedirs(os.path.join(ROOT, "Main"))
    if D["active"] not in plnames():
        D["active"] = plnames()[0]


# ---------- playback engine ----------
class Engine:
    def __init__(s):
        s.lock = threading.RLock()
        s.fm = s.dec = s.ctl = None
        s.order, s.idx, s.queue = [], 0, []
        s.playing = s.paused = s.skip = s.live = False
        s.cur, s.title, s.pos, s.dur = None, "", 0, 0

    def ensure_fm(s):
        if s.fm and s.fm.poll() is None:
            return
        if not os.path.exists(FIFO):
            os.mkfifo(FIFO)
        if s.ctl is None:
            s.ctl = os.open(FIFO, os.O_RDWR | os.O_NONBLOCK)
        s.fm = subprocess.Popen(
            [PIFM, "-freq", str(D["freq"]), "-ps", D["ps"], "-ctl", FIFO, "-audio", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        s.fm.stdin.write(b"RIFF" + struct.pack("<I", 0x7FFFFFF0) + b"WAVEfmt " +
                         struct.pack("<IHHIIHH", 16, 1, 2, 44100, 176400, 4, 16) +
                         b"data" + struct.pack("<I", 0x7FFFFFD0))
        s.rds(s.title or D["ps"])

    def restart_fm(s):
        if s.fm:
            s.fm.kill()
        s.fm = None

    def rds(s, text):
        try:
            if s.ctl is not None:
                os.write(s.ctl, ("RT %s\n" % text[:64]).encode())
        except OSError:
            pass

    def out(s, b):
        try:
            s.fm.stdin.write(b)
            s.fm.stdin.flush()
        except (BrokenPipeError, OSError, AttributeError):
            s.fm = None
            time.sleep(.5)

    def open_dec(s, entry):
        kind, name = entry.split(":", 1)
        pre, s.dur = [], 0
        if kind == "f":
            src = fpath(name)
            if not src or not os.path.exists(src):
                return None
            title = os.path.splitext(os.path.basename(name))[0]
            try:
                s.dur = float(subprocess.check_output(
                    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", src], timeout=10))
            except Exception:
                pass
        else:
            src = D["streams"].get(name)
            if not src:
                return None
            title = name
            pre = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        s.title, s.live, s.pos = title, kind == "s", 0
        s.rds(title)
        return subprocess.Popen(
            ["ffmpeg", "-loglevel", "quiet", *pre, "-i", src, "-vn",
             "-f", "s16le", "-ar", "44100", "-ac", "2", "-"],
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)

    def run(s):
        while True:
            try:
                s._loop()
            except Exception as e:
                print("engine error:", e, flush=True)
                s.fm = None
                time.sleep(2)

    def _loop(s):
        silence = bytes(8820)
        while True:
            s.ensure_fm()
            if not s.playing or s.cur is None:
                s.out(silence)
                continue
            s.skip = False
            dec = s.dec = s.open_dec(s.cur)
            if not dec:
                s.advance()
                time.sleep(.5)
                continue
            while not s.skip:
                if s.paused:
                    s.out(silence)
                    continue
                b = dec.stdout.read(8820)
                if not b:
                    break
                s.out(b)
                s.pos += len(b)
            dec.kill()
            if not s.skip:
                s.advance()

    def advance(s, step=1):
        with s.lock:
            if step > 0 and s.queue:
                s.cur = s.queue.pop(0)
                return
            if not s.order:
                s.playing, s.cur = False, None
                return
            i = s.idx + step
            if not 0 <= i < len(s.order):
                if not D["loop"]:
                    s.playing, s.cur = False, None
                    return
                i %= len(s.order)
            s.idx, s.cur = i, s.order[i]

    def start(s, pl, i=0):
        with s.lock:
            items = read_pl(pl)
            if not items:
                return
            i = min(i, len(items) - 1)
            first = items[i]
            if D["shuffle"]:
                random.shuffle(items)
                items.remove(first)
                items.insert(0, first)
                i = 0
            s.order, s.idx, s.cur = items, i, first
            s.playing, s.paused, s.skip = True, False, True
            D["active"] = pl
            save()

    def play_now(s, entry):
        with s.lock:
            s.queue.insert(0, entry)
            s.playing, s.paused = True, False
            s.advance()
            s.skip = True

    def step(s, d):
        with s.lock:
            if not s.playing:
                return
            s.advance(d)
            s.skip = True

    def stop(s):
        s.playing = s.paused = False
        s.skip = True


E = Engine()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 << 30


@app.get("/")
def index():
    return send_file(os.path.join(BASE, "index.html"))


@app.get("/api/state")
def state():
    ensure_default()
    pls = playlists()
    lib = [{"name": e[2:]} for items in pls.values() for e in items if e.startswith("f:")]
    return jsonify(freq=D["freq"], ps=D["ps"], shuffle=D["shuffle"], loop=D["loop"],
                   streams=D["streams"], active=D["active"], playlists=pls,
                   library=lib, queue=E.queue,
                   now=dict(title=E.title, playing=E.playing, paused=E.paused,
                            pos=E.pos / 176400, dur=E.dur, live=E.live, entry=E.cur))


@app.post("/api/upload")
def upload():
    ensure_default()
    folder = os.path.join(ROOT, D["active"])
    n = 0
    for f in request.files.getlist("files"):
        name = secure_filename(f.filename)
        if name.lower().endswith(EXT):
            f.save(os.path.join(folder, name))
            n += 1
    return jsonify(ok=n)


@app.post("/api/play")
def play():
    j = request.json
    if "entry" in j:
        E.play_now(j["entry"])
    elif "queue" in j:
        E.queue.append(j["queue"])
    else:
        E.start(j.get("pl", D["active"]), j.get("i", 0))
    return jsonify(ok=1)


@app.post("/api/ctl")
def ctl():
    a = request.json["a"]
    if a == "pause":
        E.paused = not E.paused
        if not E.playing:
            E.start(D["active"])
    elif a == "next":
        E.step(1)
    elif a == "prev":
        E.step(-1)
    elif a == "stop":
        E.stop()
    return jsonify(ok=1)


@app.post("/api/settings")
def settings():
    j = request.json
    restart = False
    if "freq" in j:
        f = round(float(j["freq"]), 1)
        if 76 <= f <= 108 and f != D["freq"]:
            D["freq"], restart = f, True
    if "ps" in j and j["ps"][:8] != D["ps"]:
        D["ps"], restart = j["ps"][:8], True
    for k in ("shuffle", "loop"):
        if k in j:
            D[k] = bool(j[k])
    save()
    if restart:
        E.restart_fm()
    return jsonify(ok=1)


@app.post("/api/playlist/save")
def pl_save():
    j = request.json
    name = safe(j["name"])
    os.makedirs(os.path.join(ROOT, name), exist_ok=True)
    if "tracks" in j:
        write_order(name, j["tracks"])
    D["active"] = safe(j.get("active", D["active"]))
    save()
    return jsonify(ok=1)


@app.post("/api/playlist/delete")
def pl_del():
    name = safe(request.json["name"])
    folder = os.path.join(ROOT, name)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    ensure_default()
    save()
    return jsonify(ok=1)


@app.post("/api/track/delete")
def track_del():
    rel = request.json["name"]
    p = fpath(rel)
    if p and os.path.isfile(p):
        os.remove(p)
    if E.cur == "f:" + rel:
        E.step(1)
    return jsonify(ok=1)


@app.post("/api/stream/save")
def stream_save():
    j = request.json
    D["streams"][j["name"].strip()] = j["url"].strip()
    save()
    return jsonify(ok=1)


@app.post("/api/stream/delete")
def stream_del():
    name = request.json["name"]
    D["streams"].pop(name, None)
    for pl in plnames():
        t = read_pl(pl)
        if "s:" + name in t:
            write_order(pl, [e for e in t if e != "s:" + name])
    if E.cur == "s:" + name:
        E.step(1)
    save()
    return jsonify(ok=1)


ensure_default()
threading.Thread(target=E.run, daemon=True).start()
if read_pl(D["active"]):
    E.start(D["active"], 0)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "80")), threaded=True)
