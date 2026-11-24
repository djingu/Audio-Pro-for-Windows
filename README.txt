AUDIO PRO CONTROL 3.6  -  control your Audio Pro speakers from Windows
=====================================================================

INSTALL / UPDATE
  1. Unzip this folder anywhere.
  2. Double-click Install.bat (it also updates an older version).
     - If Python isn't installed it is fetched automatically with winget (one time).
     - Start menu + Desktop shortcuts are created.
  3. The first time it runs, Windows Firewall asks about "Python" - tick
     PRIVATE networks and allow it. This is needed both to find the speakers
     and to stream your music files to them.

The app opens in its own window (it uses Microsoft Edge, built into Windows, to
draw the interface). Closing that window quits the app; minimising it does not.
It has its own taskbar button and icon: right-click it and choose
"Pin to taskbar" to keep it there.

SPEAKERS (left)
  - Found automatically. Refresh icon = search again, + = add by IP address.
  - Click a speaker to control it. Right-click it (or use ...) for details,
    Reconnect, Copy diagnostics and Remove.
  - Both speaker generations are supported and can be mixed in one group:
    first generation (A10, A26, A36, Addon C3/C5/C10, Drumfire, Link 1...)
    and the MkII generation (A10 MkII, C5 MkII, C10 MkII, A15, A28, Link 2...).
  - A speaker that is switched off is shown dimmed as "Offline" and comes back
    by itself. A removed speaker stays away until you search again.

YOUR MUSIC (middle)
  - "Add folder" and pick a folder with MP3, FLAC, M4A/AAC or WAV files.
    Titles, artists, track numbers and covers are read from the files.
  - Songs / Albums switch at the top. Click a column heading to sort, an
    artist or album name to see just that.
  - Double-click a song to play it on the selected speaker or group; the rest
    of the list follows as a queue. Right-click a song or album for
    "Play next" and "Add to queue". Click a song under "Next up" to jump to it.
  - Shuffle and Repeat are in the player bar at the bottom.
  - Songs stream from this PC, so keep the app open while they play.
  - Album covers (new in 3.5): the picture inside the music files is used
    first, then a picture next to the songs (cover.jpg, folder.jpg,
    front.jpg...). Albums with neither get their cover from MusicBrainz /
    the Cover Art Archive (free). Only the album and artist names are sent
    to musicbrainz.org; found covers are kept in
    %APPDATA%\AudioProControl\covers. Switch it off with "Missing covers"
    next to the folders.

ON THE RIGHT
  - What is playing, the speaker's inputs (Wi-Fi, Bluetooth, Line in, RCA...)
    and, on speakers that report them, the presets saved on the speaker.

PLAYER BAR (bottom)
  - Play / pause, previous / next, a progress bar you can drag, volume
    (the mouse wheel works on it) and mute.
  - Moon icon: sleep timer - pauses the music after 15 minutes to 2 hours.
  - Speaker name: tick which speakers play the same audio, set each one's
    volume, or use "Play everywhere" / "Ungroup".

KEYBOARD
  Space play/pause | Ctrl+Left/Right previous/next | Ctrl+Up/Down volume
  M mute | Ctrl+F search | Enter play highlighted song | Esc back / close

Works with Spotify Connect, AirPlay etc. too: start music from your phone as
usual and control or group it from here.

IF SOMETHING LOOKS WRONG
  Right-click the speaker > "Copy diagnostics". It copies exactly what the
  speakers report, which is what is needed to fix a problem.

UNINSTALL
  Delete %LOCALAPPDATA%\AudioProControl and %APPDATA%\AudioProControl, and
  the two "Audio Pro Control" shortcuts.

Speaker protocol details and the LinkPlay client certificate come from the
MIT-licensed pywiim project by Michael Cumming (github.com/mjcumming/pywiim).
Icons: Material Icons (Apache 2.0).
