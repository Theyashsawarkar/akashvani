# 4. Note arrival times ourselves; time do not disturb with a user timer

**Status:** Accepted  
**Date:** 2026-11-07

## Context

The redesign puts a time on every notification and offers do not disturb for an hour or till tomorrow. mako's JSON (`makoctl list -j` / `history -j`) has no times, and the panel is closed most of the time, so it can't turn do not disturb off itself.

## Decision

- akashvani watches the session bus for `org.freedesktop.Notifications.Notify` calls (a D-Bus monitor, `BecomeMonitor`, made once for the daemon's life). Only the app name, the summary and the time are kept in memory, then matched to mako's ids on the next search; the id's time is saved in `~/.local/state/vyom/akashvani-times.json`. A notification it didn't see arrive gets the time it was first listed; the ones from before akashvani watched get none ("Earlier").
- A timed do not disturb starts a transient systemd user timer (`systemd-run --user --unit=akashvani-dnd-off --on-active=…`) that runs the off command (`makoctl mode -r do-not-disturb`, or `dnd_off`). Without systemd it's a detached `sleep; off-command`. The end time is kept in `akashvani-dnd.json`.

## Consequences

- Times and timers work with the panel closed, and survive `vyom reload`; a timer survives a Vyom restart too.
- Notifications sent while Vyom wasn't running get the time akashvani first listed them.
- If the bus refuses the monitor, every new notification still gets a time, only less exact.
