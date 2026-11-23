AUDIO PRO CONTROL 3.1  -  control your Audio Pro speakers from Windows
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

SPOTIFY (middle, "Spotify" tab at the top)  - new in 3.1
  Browse your playlists, Liked Songs and saved albums, search Spotify, and
  play on the selected speaker or group. Needs Spotify Premium.

  One-time setup (about two minutes, the app walks you through it):
    1. Open developer.spotify.com/dashboard, log in with your Spotify account,
       accept the terms, press "Create app". Any name, e.g. Audio Pro Control.
    2. Under "Redirect URIs" add exactly:
           http://127.0.0.1:47811/spotify/callback
       (the app shows this with a Copy button), tick "Web API", Save.
    3. Copy the app's "Client ID" into Audio Pro Control and press Connect.
       A browser tab opens: log in to Spotify and press Agree.
  You don't need the "Client secret". The sign-in is kept in
  %APPDATA%\AudioProControl\spotify.json; "Disconnect" at the bottom of the
  Spotify page removes it.

  Using it:
  - Double-click a song, or press the green play button on a playlist, album
    or artist. Shuffle next to it applies when Spotify starts.
  - Right-click a song: "Add to Spotify queue", "Go to album", "Go to artist".
  - The speaker plays straight from Spotify, so the music keeps going even
    if this PC sleeps. "Next up" on the right shows Spotify's queue.
  - Grouped speakers: Spotify plays on the group's main speaker and the
    others follow, like any other music.
  - "Spotify can't see <speaker>": Spotify only lists speakers that are on
    and have been played to from your account. Pick the speaker once in the
    Spotify app on your phone (devices button). If Spotify knows the speaker
    by another name, pick that name in the same message.
  - Spotify's rules for personal developer apps: you can only see the songs
    of playlists you made or collaborate on. Other playlists (e.g. Spotify's
    own) still play with the play button. Searches show the top 10 of each kind.

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
  M mute | Ctrl+F search (your music or Spotify) | Enter play highlighted song
  Esc back / close

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
