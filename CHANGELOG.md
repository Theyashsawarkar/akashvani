# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

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
