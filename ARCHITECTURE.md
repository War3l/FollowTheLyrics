# Architecture

FollowTheLyrics is a desktop app: a single PyQt6 process, a transparent window
over the game, a control panel and a few worker threads. The code is organised
**by responsibility**. Only one boundary is abstract: the one with the operating
system, because it has several implementations (Windows, Linux, and a Qt-only
backend for macOS until it gets its own). Everything else has one
implementation per need and stays concrete.

## The `desktop/` layer

`desktop/ports.py` describes as `Protocol`s everything the app asks of the
system: current track, audio capture, global shortcuts, windows, foreground
program, autostart, desktop shortcuts, dialogs, installation, release format.
`desktop.current()` picks a backend once and returns a `Desktop` that groups
them.

- `desktop/windows/`: SMTC, WASAPI, `RegisterHotKey`, DWM, registry. Each
  module starts with `assert sys.platform == "win32"`, which lets mypy check
  the rest of the code for Linux without seeing these calls.
- `desktop/linux/`: MPRIS through QtDBus for the current track, PulseAudio or
  PipeWire through `soundcard` for the beat, X11 through `python-xlib` for
  global shortcuts and the foreground program, XDG for autostart and desktop
  shortcuts. On Wayland, `boot.prepare()` picks XWayland when it is there, the
  only way to keep the overlay on top. On Hyprland, which maps XWayland
  coordinates wrongly and does not let the mouse through an X window, it keeps
  native Wayland and `hyprland.HyprlandWindowing` places the overlay through
  the IPC socket. Without an X server, shortcuts and game detection are `None`
  or stay neutral.
- `desktop/generic/`: Qt only, for macOS today. Services with no portable
  equivalent are `None` and the interface hides what depends on them
  (autostart, installation, updates) or reports it (global shortcuts).

Adding a system means writing `desktop/<system>/backend.py` with a `create()`
function that fills the ports it can serve. No other file changes.

## Packages

```
src/followthelyrics/
├── __main__.py      entry point: backend startup, then app.main()
├── app.py           wires everything: overlay, panel, tray, timers, signals
├── diagnostics.py   diagnostic report and offscreen captures (--snapshot)
├── logs.py          rotating log in the data folder
├── version.py       installed version and GitHub repository
├── config/
│   ├── settings.py  data folder, config.json, default values
│   └── games.py     game profiles, forbidden zones, captures
├── lyrics/
│   ├── model.py     Line: one lyric line with its timings
│   ├── parsing.py   LRC and YRC formats, singers, ad-libs, title cleanup
│   ├── providers.py NetEase and LRCLIB, best result choice, translation
│   ├── cache.py     disk cache of lyrics found or not found
│   ├── analysis.py  choruses, strong words, per word statistics
│   └── demo_song.py demo lyrics
├── desktop/
│   ├── ports.py     contracts with the operating system
│   ├── windows/     Windows backend: SMTC, WASAPI, Win32, DWM, registry
│   ├── linux/       Linux backend: MPRIS, PulseAudio, X11, XDG, Hyprland
│   └── generic/     Qt-only backend, for macOS
├── playback/
│   ├── track.py     NowPlaying: the current track
│   ├── sites.py     recognises the browser's site, ignores videos and streams
│   ├── audio.py     audio output choice and beat detection
│   └── worker.py    Qt threads: MediaWorker (track, lyrics, cover), BeatBridge
├── overlay/
│   ├── window.py    the lyrics window: placement, animation, rendering
│   ├── effects.py   blur, palettes taken from the cover, pixel access
│   ├── colors.py    LCH colours and clustering of an image's colours
│   └── animation.py animation curves
├── ui/
│   ├── panel.py     control panel, one page per topic
│   ├── widgets.py   shared animated building blocks (cards, switches, tiles)
│   ├── welcome.py   first launch screen
│   └── zone_editor.py editor for a game's forbidden zones
└── system/
    ├── startup.py      autostart, desktop shortcut, launch command
    ├── install.py      installation, registration, uninstallation
    ├── updater.py      lookup, download and replacement of the program
    ├── certificates.py system certificates for the Linux binary
    └── hotkeys.py      key combinations and shortcut manager
```

## Dependency rules

Each package imports only what this table lists. The module graph has no
cycle.

| Package | May import |
|---|---|
| `version`, `config` | nothing internal |
| `lyrics` | `config.settings`, `version` |
| `playback` | `lyrics` |
| `desktop.ports` | `playback.track` |
| `desktop.windows`, `desktop.generic` | `desktop.ports`, `config.settings`, `playback.track` |
| `desktop.linux` | the same, plus `desktop.generic` and `playback.sites` |
| `system` | `desktop.ports`, `config.settings`, `version` |
| `overlay` | `lyrics`, `config.settings` |
| `ui` | `config`, `desktop.ports`, `system`, `playback.sites`, `version`, never `overlay` |
| `app`, `diagnostics`, `__main__` | everything, `desktop` included |

Useful consequences:

- `lyrics/` knows neither Qt nor Windows. All lyrics processing can be tested
  on any machine.
- Only `desktop/windows/` and `desktop/linux/` talk to the system. The rest
  receives the ports through its constructor (`Overlay`, `MediaWorker`,
  `AudioBeats`, `Hotkeys`, `Installation`), which lets it be tested with fake
  backends.
- The panel (`ui/`) never touches the overlay directly: `app.py` hands it the
  object and relays settings changes.

## Data flow

```
MediaBackend ──▶ MediaWorker (QThread) ──Qt signals──▶ App ──▶ Overlay
                    │                                 │
                    ├─ playback.sites (filter)         └──▶ Panel
                    ├─ lyrics.cache
                    └─ lyrics.providers ──▶ lyrics.parsing

AudioBackend ──▶ playback.audio ──▶ BeatBridge ──beat──▶ Overlay.on_beat
HotkeyBackend ──▶ system.hotkeys.Hotkeys ──pressed──▶ App
```

- Network calls, reading the current track and audio capture live in
  `QThread`s. They only talk to the main thread through Qt signals, so no lock
  is needed.
- The overlay only redraws when something moves (`is_animating`) and slows
  its timer down when idle. Text layouts, glows and palettes are cached.

## Conventions

- Google style: module imports only (`from followthelyrics.lyrics import
  parsing`, then `parsing.parse_lrc(...)`), never a relative import.
- `ruff` (lint and format, 80 columns), `mypy` for `win32` and for `linux`, and
  `pytest` pass without errors; CI runs them on every pull request.
- Attributes never shadow a Qt method (`size`, `style`, `layout`, `pos`…): a
  widget that holds a slider calls it `size_slider`.
- User data goes into `settings.DATA_DIR` (overridable with `FTL_DATA_DIR`,
  which the tests do).
