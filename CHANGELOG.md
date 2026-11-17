# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

## v0.5.0 -- 2026-11-17

- **akashvani is the notification server now** (it replaces mako): it implements the freedesktop notification spec and draws its own popups, inside the Vyom daemon that's already running, so no new process (ADR 0005).
- **Popups in your theme**: glass cards with the image or icon, app and time, title, body (its markup made safe), action buttons, and a bar for volume / brightness that moves in place. Urgent ones are framed red; hover holds a card; click runs the default action, right click dismisses, middle click dismisses all; more than `max_visible` wait behind "+N more". They slide in and out.
- **Everything is configurable**: position, size, margins, gap, timeouts per urgency, animation, layer, sound, what a card shows; every part has a CSS class to restyle it.
- **Rules** (`[[plugin.akashvani.rules]]`): by app, title, body, urgency, category, mode, actions or slider; set the timeout, hide, ignore, mute, keep out of the history, change the urgency, show in do not disturb, tint the card, add a CSS class.
- **Modes**: `dnd` / `do-not-disturb` hold popups (urgent ones still show) and mute; `silent` mutes. They survive a restart; a timed do not disturb is the daemon's own timer.
- **The history is akashvani's own**, with exact times, saved across restarts (`history_max`); volume and brightness sliders stay out of it.
- **The `akashvani` command**: `list`, `history`, `count`, `dismiss`, `restore`, `invoke`, `menu`, `mode`, `status`, `reload`, `doctor`, with makoctl's JSON, so mako scripts work by renaming the command; it passes commands to makoctl while mako still holds the name.
- The panel updates the moment a notification comes or goes, marks held ones, and shows each notification's image; the popups step aside while it's open.
- `dbus/org.freedesktop.Notifications.service`: D-Bus starts Vyom (not mako) when a notification arrives before it.
- No longer needs makoctl. While mako runs, akashvani waits for it and the panel works over mako as before; `server = false` keeps it that way.

## v0.4.0 -- 2026-11-09

- `Space u p` (show or hide the preview) now comes from Vyom core, which also remembers it per tool; the tool's own copy is gone.
- **Vim keys** (Vyom 0.7, ADR 0008): NORMAL and INSERT modes, `Space` as the leader with a which-key strip, `?` and `Space ?` list every key, `Space Space` is a palette, counts (`5j`), `gg` / `G`, `H` / `L` for tabs. It opens in NORMAL, so stray typing changes nothing; `/` searches. Needs Vyom 0.7.0.
- Its keys are data (`akashvani/vim.py`); `scripts/keybinds.py` writes the `# keybind:` lines and the README's key tables from them, and `--check` (CI) fails when they drift.
- `h` / `l` fold and open an app's stack, `d d` dismisses (no question: it stays in the history), `u` brings back the last one, `y y` copies, `Space n n/o/h/t/a` do not disturb, `Space d a` dismisses everything on screen (asks first), `Space x 1..9` runs an action, `Space f l/h/a/c` filter live, history, one app or nothing, `Space y b` copies the body, `Space u p` hides the preview.
- **Fixed**: `Ctrl+Backspace` dismissed every notification even while you typed in the search box; it's the box's word delete again (`Space d a` dismisses all, and asks).
- `Ctrl+C` and `Delete` belong to the search box while typing.
- A `Space f` filter ends when the panel closes; it no longer hid the history (or every other app) the next time it opened, with nothing saying so.

## v0.3.0 -- 2026-11-07

- **Each app's notifications are one row** with a count, instead of a heading per app; Enter opens the
  stack (and folds it again). The history is under Earlier today, Yesterday and Older.
- **A time on every notification** ("now", "2 min", "09:41"). mako keeps no times, so akashvani notes
  when each one arrives (see docs/adr/0004).
- **Urgent notifications** get a red "Urgent" chip and come first under "On screen now".
- **Do not disturb for 1 hour, till tomorrow morning (08:00, `dnd_morning`), or till you turn it off**,
  in the header; `Ctrl+N` cycles through them. A systemd user timer turns it off again, even with the
  panel closed. While it's on, the panel says until when and how many notifications it's holding.
- The preview shows the notification's own actions as buttons numbered `Alt+1..9`, Enter for its
  default action, Copy (`Ctrl+C`) and a red Dismiss (`Delete`). `Ctrl+Backspace` now dismisses
  everything on screen.
- A notification without an icon in your icon theme gets a bell instead of a broken image.
- Needs Vyom 0.6.0.

- Every corner is rounded: the website's callouts.
- A logo and a shloka at the top of the README and the website: every Vayu tool has them now.

## v0.2.0 -- 2026-11-02

- **Renamed from suchana to akashvani** (आकाशवाणी, the voice from the sky). The repository moved to
  github.com/Theyashsawarkar/akashvani (the old address redirects); `kosha update` moves an install
  over by itself; open it with `vyom akashvani`.
- Screenshots in the README and on the website.

## v0.1.4 -- 2026-10-21

- A website (GitHub Pages, https://theyashsawarkar.github.io/suchana/): the README as a home page, the
  changelog, and architecture decision records (`docs/adr/`), built from these files by
  `scripts/build-site.py`; CI checks the site is up to date.

## v0.1.3 -- 2026-10-21

- Documentation for open source: a logo and banner, a full README (features,
  install, usage, configuration, troubleshooting, the whole Vyom family),
  CONTRIBUTING, SECURITY and CODE_OF_CONDUCT, issue and pull request
  templates, and CI (compiles, checks plugin.toml and that every key is
  documented).

## v0.1.2 -- 2026-10-19

- Opens at Vyom's shared panel size (Vyom 0.2.5) like every other tool:
  its own width/height are gone.

## v0.1.1 -- 2026-10-19

- Keys are spelled out (Ctrl+Enter, Shift+Enter, Backspace) instead of symbols
  (⌃↵, ⇧↵, ⌫) in the footer and on rows and buttons.

## v0.1.0 -- 2026-10-19

- First release, as its own repository: notifications. Replaces notification-history.py in Vayu.
- What's **on screen now**, with the actions it offers (run them, or dismiss it).
- The history, **grouped by app**, newest first, with each app's icon; urgent ones flagged.
- The preview shows the whole message.
- A **do not disturb** switch (mako's `do-not-disturb` mode, or your own commands).
