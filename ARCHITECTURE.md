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
│   ├── events.py    player notifications (seeks, changes) that wake the poll
│   ├── sites.py     recognises the browser's site, ignores videos and streams
│   ├── audio.py     audio output choice and beat detection
│   └── worker.py    Qt threads: MediaWorker (track, lyrics, cover), BeatBridge
├── overlay/
│   ├── window.py    the lyrics window: placement, animation, rendering
│   ├── clock.py     playback position estimated between two player readings
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
| `desktop.windows` | `desktop.ports`, `config.settings`, `playback.track`, `playback.events` |
| `desktop.generic` | `desktop.ports`, `config.settings`, `playback.track` |
| `desktop.linux` | the same as `desktop.windows`, plus `desktop.generic` and `playback.sites` |
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

Player events (MPRIS signals, SMTC handlers) ──▶ playback.events ──wake──▶ MediaWorker
                                              NowPlaying.seek ──▶ Overlay.on_track ──▶ PlaybackClock.seeked

AudioBackend ──▶ playback.audio ──▶ BeatBridge ──beat──▶ Overlay.on_beat
HotkeyBackend ──▶ system.hotkeys.Hotkeys ──pressed──▶ App
```

- Network calls, reading the current track and audio capture live in
  `QThread`s. They only talk to the main thread through Qt signals, so no lock
  is needed.
- The overlay only redraws when something moves (`is_animating`) and slows
  its timer down when idle. Text layouts, glows and palettes are cached.

## Player signals and the clock

Between two readings, `overlay/clock.py` estimates the position. Players can
also push a change, and the app uses it as soon as it arrives.

- **MPRIS (Linux)**: `Seeked` and `PropertiesChanged` on the followed player's
  bus name. Each `MprisSession` opens its own private D-Bus connection, named
  per session, and releases it on `close()` with `disconnectFromBus`, so no
  connection is shared between sessions. A listener thread owns the
  connection, so a seek is dated when it arrives even while the main thread is
  busy. Switching the followed player disconnects the old `Seeked` and
  `PropertiesChanged` subscriptions first. Only the `PlaybackStatus`, `Rate`,
  `Metadata` and `Position` keys wake the poll, and at most once every
  `WAKE_INTERVAL_S` (0.2 s). A change that arrives inside that window is not
  lost: a single-shot timer wakes the poll when the window ends.
- **Track binding**: a seek carries the track key (title and cleaned artist)
  the listener had when it arrived. Each poll of the followed player refreshes
  that key, so a seek is matched with the track the poll saw. The seek is
  applied only to that track, so a seek sent just before a track change never
  moves the next song. A seek whose duration is unknown is applied as sent, and
  bounded only when the duration is known.
- **SMTC (Windows)**: `TimelinePropertiesChanged` gives the position and
  `last_updated_time`; the seek is dated at `now - (utc now - last_updated_time)`.
  Sessions are keyed by `(source app id, ordinal among the sessions of that app)`.
  When the keys of an application change (a session of that application opens
  or closes), every session of that application is unwatched and resubscribed,
  because the ordinal of a surviving session can change. Object identity is not
  used, so a wrapper the system returns again for the same session is not
  trusted to be the same object. Each update is compared with the previous
  reading of its session: a seek is reported when the dated position
  departs from the expected one (the previous position advanced at its rate
  while playing). An offset above `LARGE_SEEK_SECONDS` (1 s) is a seek at once.
  An offset above `SEEK_SECONDS` (0.3 s) and up to 1 s is held as pending. The
  pending reading is confirmed only by a later update, dated after it and within
  `HOLD_SECONDS` (5 s), that continues from its position within `SEEK_SECONDS`;
  a repeat of the same update never confirms it. A pending offset that the
  next update does not continue, such as a lag the player recovers from, is
  discarded. Other updates only wake the poll.
  `PlaybackInfoChanged` only wakes the poll. The SMTC dating by
  `last_updated_time` does not go through the truncation logic below, which
  is for MPRIS players only.
- **Rate**: the speed of the last positive rate the player reported is kept and
  sent with each seek. A rate of 0 (paused) does not replace it.
- **Learned gain**: a player that runs off its announced speed is followed once
  the clock has learned it. Over a 5 s window (`LEARN_SECONDS`), the clock fits
  a least-squares slope to the readings. The gain is kept only when the largest
  residual of the fit stays within 0.1 s (`LEARN_RESIDUAL`), and is then bounded
  to `[GAIN_MIN, GAIN_MAX]`, which are `1 / MAX_SPEED` and `MAX_SPEED` (1/16 to
  16), the rates `track.py` accepts. A reset (new track, new lyrics) drops the
  readings and the learning window, so a stale window never teaches a speed.
  The gain already learned is kept across the reset and replaced only by a new
  window that fits. A window that changes the gain by more than `MAX_SKEW` (5%)
  counts as a correction whatever the error it leaves, so a display that ran a
  second or more ahead holds until the track catches up instead of sliding back
  at `MAX_SKEW` for tens of seconds.
- **Truncated positions**: Firefox reports `Position` truncated to the whole
  second, while its `Seeked` carries the exact target. Three whole-number
  readings at distinct instants (`QUANTIZED_READS`) make the player quantized,
  counted only while it plays, so an exact player paused on a whole second is
  not mistaken for one and resumes at the rate it had
  (`test_an_exact_player_paused_on_a_whole_second_resumes_at_its_rate`). It is
  read as truncated or rounded, with the same reading model `r = floor(x + c)`
  where `c` is 0 or 0.5. The clock keeps a set of candidate phases (`PHASES`, 0
  and 0.5) and, for each, the interval where the true position can lie.
  Readings alone cannot separate the phases. A truncating player at position
  `x` and a rounding player at `x - 0.5` report the same whole number at every
  instant, so the phase is a half-second time shift that no reading reveals.
  Only an exact anchor narrows the set. When no cell survives a reading, the
  anchor was wrong (a seek the player ignored, for instance): the clock
  restarts from the cells it had before the anchor when they still admit the
  reading, with the phase it had then, and from the reading's own cells
  otherwise. A rewind confirmed against the anchor restarts the same way. A
  player at its announced rate that ignored a seek thus goes on with the cells
  it had already narrowed and is shown exact again
  (`test_a_quantized_player_at_its_announced_rate_ignoring_a_seek_ends_exact`).
  The cells kept from before the anchor stop moving while the player is paused
  and move again when it resumes, so a seek the player ignores while paused
  keeps them too
  (`test_a_paused_ignored_seek_revives_the_cells_from_before_it`). A paused
  reading that no cell admits revives them at once, without waiting for the
  resume, and leaves them where the pause froze them even when it is delivered
  late (`test_a_late_paused_reading_that_revives_the_cells_does_not_move_them`).
  The gain is then learned again from those cells, which always admit the
  announced rate when they are new, so the prior brings it back to 1 and the display speed follows at once: a rate fitted to a false
  anchor does not drag the display away from the middle of the new cells for
  tens of seconds
  (`test_a_rate_learned_from_an_ignored_seek_dies_with_it`,
  `test_a_gain_fitted_to_an_ignored_seek_is_dropped_with_its_cells`). The new
  cells go on narrowing with the readings that follow and explain the jumps
  they admit, so a player faster than its announced rate learns its rate again
  from them instead of restarting at every reading, which would leave the
  display at the announced rate and half a second off for good
  (`test_a_player_faster_than_announced_relearns_its_rate_after_an_ignored_seek`).
  A skip soon after a seek the player ignored is still read from the readings
  alone (`test_a_skip_after_an_ignored_seek_is_read_from_the_readings_alone`).
- **Announced rate as the prior**: while the announced rate (gain 1) still fits
  at least one phase cell, the clock keeps it, because players almost always
  play at the rate they announce. A slope fitted to the whole readings does not
  override it, and once a single phase is left the error aims at the slice of
  the cell at gain 1 rather than at the middle of the cell. A rounding player
  at 1x polled every 0.9 s after a seek to 198.4 steps by one whole second at
  every reading up to 8.1 s, which fits 1.11x as well, and the clock still
  follows 1x
  (`test_a_rounding_player_at_its_announced_rate_stays_exact_after_a_seek`).
  When the announced rate fits no cell, a learned gain that still fits every
  cell is kept, and only a gain that a cell rules out moves to the middle of
  the ratio range, so a learned 2x is not moved at every reading as the cells
  narrow (`test_a_learned_rate_that_fits_every_cell_is_kept_as_they_narrow`).
  Such a gain is proven by the cells: it stays ahead of the prior as long as it
  fits every cell, also after a restart that drops the cells without
  contradicting them, so a rate learned before a paused seek the player ignored
  is kept when playback resumes from fresh cells
  (`test_a_rate_learned_before_an_ignored_paused_seek_survives_the_resume`,
  `test_a_paused_ignored_seek_keeps_the_rate_the_cells_proved`). The proof dies
  with the cells when no cell survives a reading, but the gain itself is kept
  while it fits the cells revived from before the anchor, so a seek the player
  ignores while playing leaves the speed untouched
  (`test_a_playing_seek_the_player_ignores_keeps_the_speed_its_cells_proved`).
  When no cell from before the anchor admits the reading either, as when the
  player applies the seek a poll or more after it was sent, the fresh cells
  only take the ratios those earlier cells proved, and the clock re-anchors at
  the middle of their hull even when the gain does not change, so a seek
  applied late keeps the rate proven before it
  (`test_a_seek_the_player_applies_late_keeps_the_rate_proven_before_it`).
  A gain learned from a single reading during a hold that the next fractional
  reading drops gives back both the earlier gain and whether it was proven, so
  it cannot lend its proof to a rate no cell ever measured
  (`test_a_dropped_chance_rate_does_not_prove_the_rate_it_replaced`). A cell admits
  a reading up to `POSITION_RESOLUTION` (1e-6 s) outside either edge of its quantum
  window, so a cell narrowed to a single point by a player whose true position
  lands on whole seconds is not killed by rounding
  (`test_a_cell_narrowed_to_a_point_on_whole_seconds_survives_rounding`), and
  neither is a cell whose edge a rounding player lands on exactly
  (`test_a_rounded_reading_on_the_upper_edge_of_a_cell_keeps_it`).
  The prior only costs anything when the player runs at a rate it does not
  announce: after a seek to 198.4 polled every 0.9 s, a truncating player at
  1.2x and a rounding player at 1x read the same whole seconds up to 6.3 s,
  when they are 1.26 s apart, so no estimate serves both
  (`test_a_truncating_player_fast_and_a_rounding_one_at_rate_read_alike`). The
  contract, checked on every cell of the playback matrix and on held seeks
  against an oracle that rebuilds the feasible positions from the readings
  alone (`assert_announced_rate_contract`,
  `test_a_held_seek_off_its_announced_rate_stays_in_the_hull`):
  - a player at its announced rate is shown within 1e-6 s of its true position
    from the anchor on;
  - a player off its announced rate, while the oracle keeps both phases, is
    shown within the full width of the oracle hull of positions when the
    announced rate still fits one of the oracle cells (the prior pulls toward a
    hypothesis the readings cannot rule out), and within half that width plus
    `HULL_MARGIN` (0.08 s) when it fits none;
  - once the oracle keeps a single phase, the error is within `DEADBAND` while
    the oracle width (the full width of its cell when the announced rate still
    fits it, half that width otherwise) is at most `DEADBAND`, and within that
    width plus `HULL_MARGIN` when it is wider. The width is the one the
    readings before the instant allow: a reading that shrinks the cell under a
    small lead of the display is followed smoothly, never by a step back, so
    the display meets the narrower cell from the next reading on. A player
    near its announced rate keeps it after the second phase dies, as long as
    the surviving cell admits it, and drifts within that cell until a reading
    rules the announced rate out
    (`test_a_single_phase_player_off_its_rate_stays_in_the_width_of_its_cell`).
  - the oracle admits every ratio between `SLOWEST_REPORTABLE_RATIO` and
    `FASTEST_REPORTABLE_RATIO`, `1 / MAX_SPEED` and `MAX_SPEED`, the same
    range as the clock's gain: an oracle limited to 0.25 to 4 left out true
    ratios that the clock may adopt, so it judged a correct clock wrong on
    the edges of that range;
  - a player joined at 5.05, 12.7 or 27.45 s instead of 0 is held, on every
    rate pair of the matrix, from `CONVERGED_BY` on, to the hull of the
    offsets and rates its readings older than `SETTLE_SECONDS` plus one poll
    allow, at twice its half-width when rate 1 is feasible, never under
    `DEADBAND`, plus `HULL_MARGIN`; whole readings seen before the first
    cells chain into them, and an error the cells prove is slewed back
    within `SLEW_SECONDS` of wall time even on a slow player
    (`test_a_player_joined_mid_track_converges_within_what_its_readings_prove`).
- **Scenario grids**: five grids of whole-second, rounding and exact players
  run in the test suite, each against a bound taken from the contract rather
  than from the measured errors. The full grids carry the `slow` marker and
  run with `pytest -m slow` (or `pytest -m ""` for everything); the default
  run keeps a fixed subset of each that turns through every class of player,
  mode, poll period and target:
  - backward steps of the display are measured on every scenario, between
    two readings every 50 ms as well as at each reading. A step is allowed
    only down to the highest position that the readings (the track start
    included) still allow under the hypotheses of the scenario, the seek
    applied or ignored, with any phase before and after it. Any part of a
    step below that is counted, and none is allowed, on a grid of leads of
    0.2 to 2 s after a seek, applied or ignored, followed from the start or
    joined at the seek
    (`test_a_lead_after_a_seek_is_stepped_back_only_as_far_as_the_readings_prove`),
    and on 150 random players with and without a seek
    (`test_a_random_player_is_stepped_back_only_as_far_as_the_readings_prove`).
    A small lead after an ignored seek shows no step back over 0.05 s at all
    (`test_a_small_lead_after_an_ignored_seek_shows_no_visible_step_back`);
  - a player at twice its announced rate polled every second has twins that
    no clock can tell apart: a truncating player started anywhere in
    `[N, N + 1)` and a rounding one started in `[N - 0.5, N + 0.5)` give the
    same readings and the same reported start. The error is therefore at
    least half the width of those starts, 0.75 s, above `DEADBAND`, and the
    clock stays within it over every twin
    (`test_a_double_speed_player_polled_each_second_errs_within_its_twins`);
  - a seek the player ignores, playing or paused for 3 s, at 8 rates, 7 poll
    periods and 4 targets, is shown within `QUANTUM` of the truth from 6 s
    after the seek on; a seek of a single second is the limit, since an
    ignored seek and one applied a second late read alike forever
    (`test_a_seek_the_player_ignores_is_given_up_within_a_quantum`), and a
    forward seek applied as late as its length gives the clock exactly the
    readings of an ignored one, playing or paused
    (`test_a_forward_seek_applied_as_late_as_its_length_reads_as_an_ignored_one`);
  - each cell of that grid is also held, from 6 s after the seek on, to
    the bound of what the readings allow: the hull of the positions that a
    seek ignored or applied, with a phase switch at the resume or at the
    seek, keeps feasible, from the readings older than `SETTLE_SECONDS` plus
    one poll, at twice its half-width when rate 1 is feasible, never under
    `DEADBAND`, plus `HULL_MARGIN`, and all 1344 cells stay within it
    (`test_an_ignored_seek_errs_within_the_bound_of_what_the_readings_allow`);
  - a rounding player that switches to truncation at a resume, at the rate
    that keeps its readings, reads like the original player until the two
    rates part, and the display stays between the two truths until then
    (`test_a_mode_switch_at_a_resume_reads_alike_until_the_rates_part`);
  - a seek the player applies 0.2 to 1 s after it was sent is shown, from
    `SETTLE_SECONDS` after the player applied it, within the distance the
    delay hides (the rate times the delay) plus `QUANTUM`
    (`test_a_seek_applied_late_errs_by_no_more_than_its_delay_and_a_quantum`),
    and when the cells die on the late jump the clock is anchored again on
    them, so the display is back within half a quantum
    (`test_a_seek_applied_late_is_re_anchored_within_half_a_quantum`); the
    seek is sent on the first poll at or after its instant, so poll periods
    that do not land on it are exercised too;
  - until the player applies a late seek, the display trusts the sought
    target whenever the readings are at least `JUMP` away from it, so the
    error during the delay is the length of the seek
    (`test_until_a_late_seek_is_applied_the_display_trusts_the_sought_target`);
  - a late seek to the played position hides a rewind of the rate times the
    delay; it is absorbed to within half a quantum plus `DEADBAND` once the
    rate band proved before the seek has closed, twice the time it was proved
    over (`test_a_rewind_hidden_by_a_late_seek_is_absorbed_once_the_rate_band_closes`);
  - an exact player at twice the speed polled on half seconds reads, behind
    such a rewind, exactly like a truncating twin almost a quantum ahead, so
    the display stays between the two, its lead only shrinks as the slew
    follows the middle of the surviving cell, and it is within `DEADBAND` of
    the middle of the two once the rate band has closed
    (`test_an_exact_player_behind_a_hidden_rewind_reads_like_a_truncating_twin`);
  - cells killed by a seek the player ignores restart at the middle of the
    hull of the readings, never past the width a single phase allows
    (`test_cells_killed_by_an_ignored_seek_restart_at_the_hull_middle`), and
    the cells kept from before such a seek stop moving during a later pause,
    so the resumed display is exact again
    (`test_cells_from_before_an_ignored_seek_stop_moving_during_a_pause`);
    a seek ignored while paused resumes within the width of a single phase,
    which holds only because the cells admit a reading up to
    `POSITION_RESOLUTION` below their lower edge and an exact anchor is a box
    of that half-width
    (`test_a_paused_ignored_seek_resumes_within_the_width_of_a_single_phase`);
  - a player resumed 5 s after a pause is shown within the full width of the
    cells its readings allow, with edges closed by `POSITION_RESOLUTION` as
    the clock admits them, plus `HULL_MARGIN` when that width exceeds
    `DEADBAND`, and within `DEADBAND` otherwise
    (`test_a_resume_stays_in_the_width_of_the_cells_proved_before_the_pause`);
  - a rewind of 15 s the clock was not told about is followed within half a
    quantum from 5 s after it, since an exact player polled on whole seconds
    reads like a truncating one
    (`test_an_unannounced_rewind_is_followed_within_half_a_quantum`);
  - a seek the player drops is given up, and the display is back within
    `DEADBAND`, from `CONFIRM_SECONDS` after the first reading past
    `SETTLE_SECONDS`, when the rewind back to the played position is confirmed
    (`test_a_seek_the_player_drops_is_given_up_once_its_rewind_is_confirmed`).
- **Explained jumps**: a whole-second reading that jumps by at least `JUMP`
  (1 s) resets the clock as a new position, unless the truth cells already
  explain it. A reading is explained when, after the cells have been sheared to
  its instant, one phase cell still meets the quantum window
  `[position - phase, position + QUANTUM - phase]`. An explained jump keeps the
  anchor and narrows the cells, and it counts as a correction, so the display
  follows at once instead of sliding for `SLEW_SECONDS` (2 s). The cells
  explain jumps on an anchored clock, and also on a quantized one after a
  restart, when they only come from the readings since: a player at three
  times its announced rate that ignored a seek would otherwise restart at
  every reading and stay at the announced rate for good
  (`test_a_player_faster_than_announced_relearns_its_rate_after_an_ignored_seek`).
- **Exact rate mismatch**: an exact player (whole seconds are not required)
  whose readings advance at a rate inside `SEEK_RATIO_LOW` to
  `SEEK_RATIO_HIGH`, in jumps of more than `SETTLE` (0.3 s), is relearned once
  `MISMATCH_READS` (3) consecutive readings agree within `MAX_SKEW`. The gain
  is multiplied by the observed ratio, and the clock is re-anchored on the
  reading. Smaller jumps keep the usual steering, so a 10% speed difference
  polled every 0.4 s is still absorbed by slewing.
- **Backward jump**: a reading at least `JUMP` (1 s) behind the clock is
  doubted. It is confirmed as a rewind when the readings that follow keep to
  it for `CONFIRM_SECONDS` (1 s), within `SETTLE` for a precise player and
  within one `QUANTUM` for a quantized one, since two whole readings of a
  playing track differ from its advance by up to a second. A quantized rewind
  polled every 0.25 to 0.5 s is therefore confirmed instead of staying doubted
  for good (`test_a_quantized_rewind_polled_quickly_is_confirmed`). While it
  is doubted, a whole
  reading that still moved forward since the last accepted reading relearns
  the rate from the truth cells at once, and a doubted reading the cells
  explain narrows them. A rate learned far too high from the first readings
  is corrected instead of leaving the display running ahead while every
  reading stays doubted. A whole reading that the cells explain and that is
  not behind the last accepted one is never doubted, even when the display is
  more than `JUMP` ahead of it: a quantized player repeats its whole second,
  and that repeat is not a rewind. A confirmed rewind, or any jump of `JUMP`
  or more, resets the clock unless the cells explain the reading or the cells
  kept from before the anchor revive on it. Only a whole reading revives
  them, since they are cells of whole-second readings.
- **Track start off a whole second**: a track that starts playing at a
  position of at least `QUANTUM` that is not a whole second keeps that start
  as the cells kept from before the anchor, a box of `POSITION_RESOLUTION`
  around it at every reportable ratio. It is not an anchor: the display
  follows the readings as before. A confirmed rewind revives it, so a player
  slower than announced is narrowed from its real start instead of restarting
  at the lower edge of the reading
  (`test_a_random_player_is_stepped_back_only_as_far_as_the_readings_prove`,
  seed 15). A jump forward drops it instead, because a fast player read early
  admits a wide band of ratios from its start and adopting their middle would
  overshoot and then step back
  (`test_a_fast_player_from_its_track_start_shows_no_visible_step_back`).
- **Display ahead after a correction**: a display ahead of the estimate waits
  for the track instead of stepping back, so small leads never show a backward
  jump. A correcting reading (it rules out a phase, explains a jump, or changes
  the learned gain once a single phase is left) that leaves the display more
  than `HOLD_LEAD` (0.3 s) ahead moves it back at once, and so do a rate
  relearned while a seek is held and cells revived by a rewind. The step back
  goes only as far as the highest position still possible (`_proven_upper`:
  the upper edge of the truth hull, or of the cells kept from before a seek
  while they still admit the readings), never down to the estimate when the
  estimate is lower: the display holds at that position until the estimate
  reaches it (`_approach`). A step back is then never larger than what the
  readings prove, which the tests measure on every scenario (see the
  backward-step grids below). A reading taken at the very instant of a held
  seek gives no elapsed time to learn a rate from, so it relearns nothing.
- **Stall patience for quantized players**: a quantized player that holds its
  last whole reading is stalled only after one quantum at its effective rate,
  `QUANTUM / (speed * gain)`, or the usual patience if that is longer. A
  half-speed player is therefore not frozen between two of its steps.
- **Slope after the alias dies**: once one phase survives and the ratio range
  of its cell is within `ERR_PIN` (0.2) and the announced rate no longer fits
  it, the error is the midpoint of the cell projected to the current instant at
  the announced speed, not the midpoint of the ratio range times the elapsed
  time. The cell is the feasible set of origin and ratio since the last anchor,
  so its projection narrows as the readings accumulate, while a gain error
  would drift with time. The learned gain is not changed by this rule.
- **Exact anchors**: four events give an exact position, and each one keeps
  the mode (`_phases`, learned per application identifier and kept across
  tracks of that application) once the candidates collapse to one. An exact
  anchor starts again from both phases, so it revises a remembered mode:
  - the start of a track at position 0 (`reset(track_start=True)`);
  - a `Seeked` target, which is exact in microseconds. A seek moves the
    position, not the rate, so when the cells before it came from an anchor
    the target's box keeps only the ratios they admitted, and a player that
    ignores the seek is followed at the rate it had proved
    (`test_an_ignored_playing_seek_is_followed_at_the_rate_proved_before_it`).
    An exact player that was never anchored still has its last reading: when
    it has a fraction of a second, that reading is the position before the
    seek, kept as the rival cells (`_exact_reading_cells`), so the hypothesis
    of an ignored seek stays open for it too;
  - a `PlaybackStatus` change to `Paused`, dated at reception by the private
    listener. The paused value is frozen at that time, and the bounds are
    advanced to it, only when the interval is pinned (width at most
    `PIN_WIDTH`, 0.05 s). Otherwise the position is not exact, and the value
    is only the clock's estimate;
  - a `PlaybackStatus` change to `Playing`, dated at reception. When the
    paused value is pinned, playback resumes from that value at the edge
    time, and the cells of every phase become one cell, the convex hull of
    the cells the clock had. The resume is exact at 1x and at 2x, a player
    that reads in the other mode after the resume is followed exactly
    (`test_a_pinned_resume_revises_the_reading_mode`), and the rates the
    cells proved before the pause are kept, so a player whose cells were
    revived while paused resumes at its rate
    (`test_a_resume_keeps_the_rate_of_cells_revived_while_paused`). Otherwise the edge
    time still dates the restart, but the position stays unknown until the
    probe narrows it.
  An exact anchor is a box of width `2 * POSITION_RESOLUTION` (1e-6 s on each
  side) around the anchored position in every phase, because MPRIS reports
  `Seeked` and `Position` in whole microseconds and SMTC in 100 ns ticks, so a
  boundary a microsecond away from a whole second is a rounding of the report,
  not a different position. A player at its announced rate that lands on or
  beside a reading boundary after a seek is therefore not cut out of its own
  cell (`test_a_seek_at_rate_is_exact_on_and_beside_the_reading_boundaries`).
  Edges are recorded by the listener thread with their reception time and
  are applied in order by the overlay, before the poll and any reading of the
  probe. An edge that arrives inside the wake window is recorded at once, but
  the wake is still rate limited.
- **Transition probe**: a quantized player's phase is pinned only by the
  moment its position changes whole second. The listener thread therefore
  runs a bounded probe after a `Playing` edge, a seek while playing, or a
  track change while playing. The schedule lives in `playback/probe.py` and
  is driven by a single-shot precise timer on the followed player's private
  connection: one `Get` of `Position` per read, with a 100 ms timeout
  (`POSITION_TIMEOUT_MS`). The first reads come every 50 ms (`SCAN_SECONDS`)
  until the first whole-second change. That change is bracketed by the last
  two reads, and the probe then plans nine reads spaced 12.5 ms
  (`REFINE_SECONDS`, `REFINE_STEPS`) centred one period (1 / rate) after the
  bracket's midpoint, so they land on the next transition. The probe stops
  after two transitions (`PROBE_TRANSITIONS`), or when `PROBE_SECONDS` (2 s)
  pass without one; each transition restarts that deadline. At most
  `PROBE_READS_PER_SECOND` (20) reads run in any rolling second, and a read
  refused by that budget is rescheduled, not dropped. A poll that reads a
  whole second on a playing player also starts it, unless the current track
  already has its transitions timed. A `Paused` edge, a player change, a
  close, or a reading with a fraction of a second stops it at once, so a
  player that reports exact positions is probed for one call. Each whole
  reading is dated at its arrival and fed to the clock like a poll, through
  the same notice path. The poll interval (0.4 s) is unchanged.
- **Pre-anchor residual**: when no anchor has been seen for an application
  since launch, the phase is unknown. A reading cannot tell `floor(x)` from
  `floor(x + 0.5)`, so the two phases stay half a second apart and their union
  is at least 0.5 s wide. The probe narrows each phase to a bracket of about
  12.5 ms of time (0.0125 position at 1x), and the clock estimates the midpoint
  of the union. Measured with the production `Probe` class in the clock model
  of `test_a_probed_quantized_player_settles_within_its_pre_anchor_bound`,
  over 20 offsets with a 0.4 s poll, the worst error after 20 s is 0.2447
  (truncated, 1x), 0.2385 (truncated, 2x), 0.2572 (rounded, 1x) and 0.2634
  (rounded, 2x). With the probe's rate reported 3% high or low, the worst is
  0.2717 (truncated, 1x, rate 3% high), and every case stays at or below
  0.28, the bound the test asserts.
  Without the probe the bound is out of reach on the 0.4 s poll grid. A 0.4 s
  poll at 1x only samples five fractional positions, so a rounded truth at
  12.3 and a truncated truth at 12.99 give the same readings forever, and any
  estimate is at least 0.345 s off one of them. The clock stays within 0.01 s
  of that floor, at 0.3492
  (`test_on_the_poll_grid_two_pre_anchor_truths_apart_read_the_same`). A
  0.1 s poll samples finer positions and tells these two truths apart, so the
  floor is a property of the 0.4 s grid, not of the readings in general.
- **Unanchored mode switch**: the learned mode is kept until an exact anchor
  contradicts it. A player that switches between truncated and rounded
  positions with no exact anchor in between stays up to about 0.5 s off until
  the next anchor, because the switch is a half-second time shift that the
  readings cannot show.
- **Signalled seek hold, playing**: after a seek during playback, the clock
  holds the signalled target and ignores readings that disagree with it, until
  a reading confirms the target (within `DEADBAND`) or `SETTLE_SECONDS` (2 s)
  pass. A whole reading held this way still narrows the truth cells of an
  anchored clock when it advanced from the target at a ratio between
  `SEEK_RATIO_LOW` and `SEEK_RATIO_HIGH`, give or take one `QUANTUM`. When the
  narrowed cells no longer fit the gain, the gain is learned from them at once
  and the display moves to the middle of the cells, so a player faster than
  announced is followed during the hold
  (`test_a_held_seek_off_its_announced_rate_stays_in_the_hull`). A reading
  outside that ratio is not taken as evidence about the target: a stale
  reading sent with the seek leaves the target in place and the rate intact
  (`test_a_seek_read_one_poll_late_keeps_its_target_then_follows`), and a
  precise player that ignores the seek is not given the rate needed to reach
  it (`test_a_precise_player_ignoring_a_seek_is_not_given_the_rate_to_reach_it`).
  A rate learned this way before the player has sent `QUANTIZED_READS` (3)
  whole readings in a row stays provisional: the first reading that is not a
  whole second proves the player precise, so the whole reading was a
  coincidence. The gain goes back to its value before the hold and the clock
  restarts on that reading, which bounds the error of an exact player that
  ignores a seek by the jump it ignored
  (`test_an_exact_player_ignoring_a_seek_never_learns_from_a_whole_reading`).
  Any held
  reading that advanced from the last accepted reading at a ratio between
  `SEEK_RATIO_LOW` and `SEEK_RATIO_HIGH` becomes the base of the next jump, so
  a player running faster than announced is not read as a jump once the hold
  ends.
- **Signalled seek hold, paused**: a seek sent while paused is held with no time
  limit, as long as the readings stay paused and report either the target or
  the position shown before the seek. The hold is released by a reading that
  reports another position, by playback resuming (the readings after resume
  then decide, with the normal confirmation within `SETTLE_SECONDS`), or by a
  track change. A player that refuses a paused seek and keeps its old position
  therefore stays on the target until it moves or resumes.
- **Resume**: when playback resumes, the clock continues from the target of the
  seek, or from the pinned paused value, at the reception time of the `Playing`
  edge (see the exact anchors above). Its `Seeked` is exact (in microseconds)
  and is sent when the seek is made, paused or playing.
- **Trust model**: any local process that owns a unique
  `org.mpris.MediaPlayer2.*` name can send a fake `Seeked` or
  `PropertiesChanged` and move the lyrics. The app filters by interface and
  keys, not by sender identity. The effect is limited to the displayed lyrics
  position.

## Conventions

- Google style: module imports only (`from followthelyrics.lyrics import
  parsing`, then `parsing.parse_lrc(...)`), never a relative import.
- `ruff` (lint and format, 80 columns), `mypy` for `win32` and for `linux`, and
  `pytest` pass without errors; CI runs them on every pull request.
- Attributes never shadow a Qt method (`size`, `style`, `layout`, `pos`…): a
  widget that holds a slider calls it `size_slider`.
- User data goes into `settings.DATA_DIR` (overridable with `FTL_DATA_DIR`,
  which the tests do).
