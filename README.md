<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg">
    <img alt="suchana" src="assets/banner-dark.svg" width="560">
  </picture>
</p>

<p align="center">
  <b>Notifications (mako): what's on screen with its actions, the history grouped by app, a full preview, do not disturb.</b><br>
  Notifications. A tool for <a href="https://github.com/Theyashsawarkar/vyom">Vyom</a>, keyboard-driven panels for Wayland.
</p>

<p align="center">
  <a href="https://github.com/Theyashsawarkar/suchana/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Theyashsawarkar/suchana/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/Theyashsawarkar/suchana/releases"><img alt="Release" src="https://img.shields.io/github/v/release/Theyashsawarkar/suchana?color=cba6f7&label=release"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-f5e0dc"></a>
  <a href="https://github.com/Theyashsawarkar/vyom"><img alt="Vyom 0.2.5+" src="https://img.shields.io/badge/vyom-0.2.5%2B-89b4fa"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-a6e3a1">
  <img alt="Wayland" src="https://img.shields.io/badge/wayland-layer--shell-94e2d5">
</p>

<!-- No screenshot: notifications shows personal data (your own notifications). -->

<p align="center">
  <img alt="suchana: an urgent notification on screen, the history grouped by app, and the picked one's details with Dismiss and Copy; a do-not-disturb switch at the top" src="assets/screenshots/suchana.png" width="100%">
</p>
<p align="center"><sub>Screenshots use made-up demo notifications.</sub></p>

> *Suchana* (सूचना) is Sanskrit for "notice": the notices your apps send you.

suchana is notifications for [Vyom](https://github.com/Theyashsawarkar/vyom): one keyboard-driven panel that opens instantly, with live data, a preview and a key for everything. It runs on any compositor with the layer-shell protocol (sway, Hyprland, river, niri, Wayfire, labwc…). In [Vayu](https://github.com/Theyashsawarkar/vayu), the desktop it was built for, it replaces notification-history.py.

## Contents

- [Features](#features)
- [Install](#install)
- [Usage](#usage)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [The Vyom family](#the-vyom-family)
- [Contributing](#contributing)
- [License](#license)

## Features

- What's **on screen now**, with the actions it offers (run them, or dismiss it).
- The history, **grouped by app**, newest first, with each app's icon; urgent ones flagged.
- The preview shows the whole message.
- A **do not disturb** switch (mako's `do-not-disturb` mode, or your own commands).
- Keyboard first: every action has a key, shown in the footer; the mouse works too.
- Never freezes the panel: slow commands run in the background.

## Install

### Requirements

- [Vyom](https://github.com/Theyashsawarkar/vyom) 0.2.5 or newer (Python 3.11+, PyGObject, GTK 4, [gtk4-layer-shell](https://github.com/wmww/gtk4-layer-shell), a Nerd Font)
- `makoctl`

### Install

```sh
git clone https://github.com/Theyashsawarkar/suchana ~/.local/share/vyom/plugins/suchana
vyom reload           # pick it up (or log out and in)
vyom suchana            # open it; run it again to close
```

Give it a key in your compositor, e.g. sway:

```sh
bindsym $mod+<key> exec vyom suchana
```

### Update and uninstall

```sh
git -C ~/.local/share/vyom/plugins/suchana pull && vyom reload     # update
rm -rf ~/.local/share/vyom/plugins/suchana && vyom reload          # uninstall
```

## Usage

Open it with `vyom suchana` (or your key). Type to search; the footer always shows the keys for what's selected.

| Key | Action |
|---|---|
| `Enter` | Run the notification's default action, or copy its text |
| `Ctrl+C` | Copy the notification's text |
| `Ctrl+Backspace` | Dismiss the on-screen notification |
| `Ctrl+N` | Turn do not disturb on or off |
| `Esc` | Close the panel |

Every Vyom panel also has `Up`/`Down` (or `Ctrl+K`/`Ctrl+J`) to move, `Page Up`/`Page Down` to jump and `Tab` to switch to the next tool.

## Configuration

Everything is optional, in `~/.config/vyom/config.toml` under `[plugin.suchana]`:

| Setting | Default | What it does |
|---|---|---|
| `dnd_status` | (makoctl mode) | Command printing the current mode |
| `dnd_on_when` | ^dnd$ | Regex: do not disturb is on |
| `dnd_on / dnd_off` | (makoctl mode -a/-r) | Commands to turn it on / off |

Run `vyom reload` after editing.

## Troubleshooting

- **Nothing opens.** `vyom list` shows every installed tool, and why one is skipped (a missing requirement, or a Vyom that's too old).
- **It opened, then something failed.** Look for a `Traceback` in the daemon's log, `journalctl --user -u vyom -u vyom-daemon -b` (without systemd: `~/.local/state/vyom/daemon.log`), and [open an issue](https://github.com/Theyashsawarkar/suchana/issues/new/choose) with it.
- **No blur or rounded corners.** That's the compositor: on SwayFX, add `layer_effects "vyom" { blur enable; corner_radius 20; shadows enable }`.

## The Vyom family

Each tool is its own repository, so you install only the ones you want:

| Tool | | What it does |
|---|---|---|
| [dvara](https://github.com/Theyashsawarkar/dvara) | द्वार, gateway | The app launcher |
| [ganit](https://github.com/Theyashsawarkar/ganit) | गणित, mathematics | The calculator and converter |
| [smriti](https://github.com/Theyashsawarkar/smriti) | स्मृति, memory | Clipboard history |
| [bhava](https://github.com/Theyashsawarkar/bhava) | भाव, feeling, emotion | The emoji picker |
| [tarang](https://github.com/Theyashsawarkar/tarang) | तरंग, wave | Wi‑Fi and the hotspot |
| [setu](https://github.com/Theyashsawarkar/setu) | सेतु, bridge | Bluetooth |
| [doot](https://github.com/Theyashsawarkar/doot) | दूत, messenger | Your phone, through KDE Connect |
| [patra](https://github.com/Theyashsawarkar/patra) | पात्र, vessel | Docker containers |
| [suchana](https://github.com/Theyashsawarkar/suchana) (this one) | सूचना, notice | Notifications |
| [raga](https://github.com/Theyashsawarkar/raga) | राग, melody | YouTube music and video |
| [mudra](https://github.com/Theyashsawarkar/mudra) | मुद्रा, gesture | Keybinding search |
| [urja](https://github.com/Theyashsawarkar/urja) | ऊर्जा, energy | The battery at a glance |
| [vishram](https://github.com/Theyashsawarkar/vishram) | विश्राम, rest | The power menu |
| [kendra](https://github.com/Theyashsawarkar/kendra) | केन्द्र, centre | Quick settings |

## Contributing

Bug reports, ideas and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and the few rules every tool follows, and [CHANGELOG.md](CHANGELOG.md) for what changed in each release. Please report security issues privately ([SECURITY.md](SECURITY.md)).

## License

[MIT](LICENSE).
