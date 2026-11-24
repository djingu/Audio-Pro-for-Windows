# Audio Pro Control

[![Latest release](https://img.shields.io/github/v/release/djingu/Audio-Pro-for-Windows?label=download&color=1ed760)](https://github.com/djingu/Audio-Pro-for-Windows/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Control your **Audio Pro Wi-Fi speakers from Windows 11**: play, pause and set the volume, switch inputs, group speakers so they play the same music, and play the music files on your PC. It has a black and silver look.

Works with both Audio Pro speaker generations, and you can mix them in one group:

- **First generation:** A10, A26, A36, Addon C3 / C5 / C10, Drumfire, Link 1 and others
- **MkII generation:** A10 MkII, C5 MkII, C10 MkII, A15, A28, Link 2 and others

![Your music library](docs/library.png)

## Features

- **Finds your speakers automatically** and remembers them, even when their IP address changes. You can also add one by IP address.
- **Now playing** for anything on the speaker, including Spotify Connect, AirPlay, Bluetooth, internet radio and Line in, with play / pause, next / previous, seek and volume.
- **Multiroom groups:** tick which speakers play together, set each one's volume, or press *Play everywhere*. Older speakers that group over Wi-Fi Direct are handled too.
- **Your music:** add folders with MP3, FLAC, M4A/AAC or WAV files. Tags are read from the files. Browse by song or album, search, and use a play queue with shuffle and repeat. The PC streams the music to the speaker.
- **Album covers:** taken from the music files, or from a picture next to them (`cover.jpg`, `folder.jpg`, `front.jpg`…). Albums with neither get their cover from [MusicBrainz](https://musicbrainz.org) and the [Cover Art Archive](https://coverartarchive.org), free and without an account.
- **Spotify, AirPlay and more:** start music from your phone as usual (Spotify Connect, AirPlay, Bluetooth), then control it and group speakers from here.
- **Inputs and presets:** switch between Wi-Fi, Bluetooth, Line in and RCA, and start the presets saved on the speaker.
- Sleep timer, keyboard shortcuts, and its own taskbar icon that you can pin.

![Grouping speakers](docs/grouping.png)

## Install

1. Download **AudioProControl-3.6.zip** (or the newest version) from the [latest release](https://github.com/djingu/Audio-Pro-for-Windows/releases/latest) and unzip it anywhere. (Or click the green **Code** button on this page → **Download ZIP**; it contains the same files.)
2. Double-click **Install.bat**. It also updates an older version.
   - If Windows asks whether to run it, choose **Run** (or **More info → Run anyway**).
   - If Python 3 isn't installed, the installer fetches it with `winget` (one time, about 30 MB).
   - The app is copied to `%LOCALAPPDATA%\AudioProControl`, and Start menu and Desktop shortcuts are added.
3. The first time the app runs, Windows Firewall asks about **Python**. Tick **Private networks** and allow it. The app needs this to find the speakers and to stream your music files to them.

The app opens in its own window. It uses Microsoft Edge, which is built into Windows, to draw the interface. To keep it on the taskbar, right-click its taskbar button and choose **Pin to taskbar**.

**Requirements:** Windows 11 (Windows 10 should work too), and the PC on the same home network as the speakers. Python 3.10 or newer is installed automatically if needed. The app uses only the Python standard library, so there are no packages to install.

## Keyboard

| Key | Action |
|---|---|
| Space | Play / pause |
| Ctrl + ← / → | Previous / next |
| Ctrl + ↑ / ↓ | Volume |
| M | Mute |
| Ctrl + F | Search your music |
| Enter | Play the highlighted song |
| Esc | Back / close |

## If something doesn't work

- **No speakers found:** check that the PC is on the same network as the speakers and that Python is allowed through the firewall on *Private* networks. You can also add a speaker with **+** and its IP address.
- **Your music won't play on a speaker:** the speaker has to be able to reach the PC. This is the same firewall setting as above.
- Right-click a speaker and choose **Copy diagnostics**. It copies exactly what the speaker reports. Include it if you [open an issue](../../issues).

## Optional: build a standalone .exe

Run **Build-Exe.bat**. It uses PyInstaller to build `dist\Audio Pro Control.exe`, which runs without Python installed.

## How it works

The app is one Python file (`AudioProControl.pyw`) and its interface (`ui.html`). The interface is served on `127.0.0.1` only, so it can't be reached from other computers.

- **Speakers:** the app talks to the speakers' local LinkPlay HTTP API and to UPnP. First-generation speakers use HTTP; MkII speakers use HTTPS on port 4443 with a client certificate.
- **Your music:** files are streamed from a small built-in media server.
- **Missing covers:** looked up on MusicBrainz one album at a time (at most one request a second, as MusicBrainz asks), and the front cover is downloaded from the Cover Art Archive. Only album and artist names are sent. Found covers are kept in `%APPDATA%\AudioProControl\covers`, so each album is asked about once. Albums without a match are tried again after 30 days. Switch it off with **Missing covers** next to your music folders.

Settings are stored in `%APPDATA%\AudioProControl`.

**Uninstall:** delete `%LOCALAPPDATA%\AudioProControl` and `%APPDATA%\AudioProControl`, and the two *Audio Pro Control* shortcuts.

## Credits

- The speaker protocol details and the LinkPlay client certificate come from [pywiim](https://github.com/mjcumming/pywiim) by Michael Cumming (MIT). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Icons: [Material Icons](https://fonts.google.com/icons) (Apache 2.0).
- Missing album covers: [MusicBrainz](https://musicbrainz.org) and the [Cover Art Archive](https://coverartarchive.org).

This is an independent project. It is not made by or affiliated with Audio Pro or LinkPlay. *Audio Pro* is a trademark of its owner.

## License

[MIT](LICENSE)
