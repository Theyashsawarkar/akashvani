# 5. Be the notification server, inside the Vyom daemon

**Status:** Accepted (supersedes 0003; 0004 now applies only over another daemon)  
**Date:** 2026-11-17

## Context

Over mako, akashvani could only show what mako kept: no times (0004 watched the bus to guess them), polling `makoctl` for changes, and popups akashvani didn't draw. mako's popups can't show action buttons, animate, size to their text or use the theme's CSS, and its margin is part of its surface, which SwayFX blurred as a sharp strip. The desktop wanted one look everywhere and fully customisable notifications.

## Decision

- akashvani implements the freedesktop notification spec (1.2) and owns `org.freedesktop.Notifications` itself (`akashvani/server.py`), with its own popups (`akashvani/toast.py`: one layer-shell window, namespace `notifications`, GTK 4 cards styled by CSS in the theme's colours).
- It runs **inside the resident Vyom daemon** (made when the plugin loads), not as its own process: GTK, gtk4-layer-shell and the theme are already loaded there, so the server costs a few MB, not another 60. The Vyom daemon is a supervised user unit; a D-Bus activation file starts it if a notification comes first.
- The name is requested with REPLACE and a place in the queue: while mako (which doesn't allow replacement) holds it, akashvani waits and the panel uses makoctl as before; it takes over when mako exits. `server = false` turns the server off.
- A control interface `dev.vayu.Akashvani` on the same connection, and an `akashvani` command speaking makoctl's commands and JSON, so scripts move from mako by renaming the command (and fall back to makoctl while mako runs).
- The history (closed ones, with times) and the modes are akashvani's own, saved in `~/.local/state/vyom/akashvani-*.json`; a timed do not disturb is a GLib timer in the daemon, re-armed after a restart.
- Rules (`[[plugin.akashvani.rules]]`) match like mako's criteria and decide timeout, hiding, sound, history, urgency and tint.

## Consequences

- One process fewer, exact times, live updates in the panel, popups as customisable as any Vyom panel.
- If the Vyom daemon crashes, notifications stop until systemd restarts it (seconds); apps that send meanwhile get an error or wait for activation.
- A slow main loop in Vyom (a plugin blocking it) would delay notifications: Vyom's rule that nothing blocks the main loop now matters for notifications too.
- The popups need gtk4-layer-shell (Vyom needs it anyway); without it, notifications still reach the panel.
