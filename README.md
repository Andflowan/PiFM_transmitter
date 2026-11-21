# PiFM_transmitter

Turn a Raspberry Pi into a small FM radio station with a **web dashboard**.
Upload music, organise playlists, play web-radio streams, change the frequency and see what is playing, all from your phone or PC on the local network.

It uses [PiFmRds](https://github.com/ChristopheJacquet/PiFmRds) to transmit on FM through **GPIO 4** (a plain wire is the antenna).

## Features

- Playlists = **folders**, tracks = **files** (MP3, FLAC, WAV, OGG, M4A, AAC, Opus)
- Upload, delete, reorder (drag & drop or arrows) from the browser
- Play / pause / next / previous / stop, shuffle, loop, "play next" queue, progress bar
- Internet radio streams, usable on their own or inside playlists
- RDS: station name and current track title shown on FM radios
- Change the FM frequency from the dashboard
- Optional network share (Samba) so you can manage playlists from Explorer / Finder
- Starts at boot and resumes playing
- Mobile friendly, no password (see the security note)

## Requirements

- Raspberry Pi **Zero, 1, 2, 3 or 4** (tested design target: Pi 3B+). **Pi 5 is not supported.**
- **Raspberry Pi OS (32-bit)**, Lite is fine. **64-bit does not work** with PiFmRds.
- SD card of 8 GB or more
- A wire of about 20 cm on **physical pin 7 (GPIO 4)** as the antenna
- Internet access during installation

## Install

```bash
git clone https://github.com/YOUR_USER/PiFM_transmitter.git
cd PiFM_transmitter
sudo ./install.sh            # add --samba to also share the playlists folder on the network
```

Then open `http://<pi-ip>` in a browser (find the IP with `hostname -I`) and tune an FM radio to **99.9 MHz**, close to the Pi.

## Using it

1. **Files** tab: upload audio into the active playlist.
2. **Playlists** tab: pick or create a playlist, click a track to play it, drag to reorder.
3. **Web radios** tab: save a stream URL, play it or add it to the active playlist.
4. **Settings** tab: frequency and RDS name.

### Playlists as folders

Everything lives in `/opt/PiFM_transmitter/playlists/`:

```
playlists/
  Main/
    song1.mp3
    song2.flac
    order.txt        (optional)
  Party/
    ...
```

- New playlist: create a folder (or use the dashboard).
- New track: drop the file in the folder.
- Play order: alphabetical by default. The dashboard writes `order.txt` when you reorder. You can also edit it by hand: one file name per line, and `s:Name` to include a saved web radio. Files not listed are appended at the end.
- With `--samba`, the folder is shared as `\\<pi-ip>\playlists`.

A playlist that is already playing keeps its order until you start it again from the dashboard.

## Manage the service

```bash
sudo systemctl restart PiFM_transmitter
sudo systemctl status PiFM_transmitter
sudo journalctl -u PiFM_transmitter -n 50 --no-pager
sudo ./uninstall.sh          # add --purge to delete the music too
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `uname -m` shows `aarch64` | You run a 64-bit OS. Re-flash Raspberry Pi OS **32-bit**. |
| Track shows as playing but no sound | Check the wire is on **pin 7**, radio on the right frequency, and that you are within 1-2 m. |
| Crackling | Try a shorter or longer wire, move the Pi away from its power supply. |
| Dashboard does not load | `sudo systemctl status PiFM_transmitter`, then read the journal. |
| Installer says not enough space | Use a larger SD card. |

## Security note

There is **no authentication**. Anyone who can reach the Pi's web port can control the radio and upload or delete files. Use it on a trusted home network only and **never expose it to the internet**.

## Legal notice

Transmitting on the FM band is regulated in most countries and often requires a licence, even at very low power. Interference with other services (including aviation) is possible. Use at your own risk, keep the range to a few metres, use only a short wire, and check your local law first. For permanent use, a legal FM transmitter module is the safe option. The authors take no responsibility for misuse.

## Credits

- [PiFmRds](https://github.com/ChristopheJacquet/PiFmRds) by Christophe Jacquet (GPLv3). It is downloaded and compiled by the installer and is not bundled in this repository.
- Dashboard and playback engine: MIT licence, see `LICENSE`.
