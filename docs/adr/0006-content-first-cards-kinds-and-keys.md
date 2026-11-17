# 6. Content-first cards, kinds of card, and keys

**Status:** Accepted  
**Date:** 2026-11-17

## Context

The first popups (0005) were a glass card per notification: a 44 px icon tile on every card, a gradient and an accent border, big pill buttons, a "+N more" pill. They read as generic, every notification looked the same whether it was a volume change, a failed deploy or a phone call, a burst from one app took every place on screen, and acting on one needed the mouse. The desktop is used by a developer at a keyboard, in dark and light themes picked in one place (varna).

## Decision

- **Content first.** The title leads; the app's 16 px icon, its name and the time sit on one quiet line above it. A picture appears only when the notification brings one (or a person's initials for calls and messages). Paths, branches, file names and `code` in a body are set in the theme's mono font. A 2 px hairline at the bottom is the time left (it stops while the pointer is on the card); a card that waits for you has none.
- **Colour only with meaning:** red for urgent (a rail and a tag in words, never colour alone) and Decline, green for a live call and Answer, yellow for held, the accent for the focused card.
- **Kinds** (`server.classify`): normal, urgent, slider (one slim line), and ekatva's call, missed call, text and phone app. ekatva tags them (`x-ekatva-kind`, `-device`, `-contact`, `-number`, `-app`); older ekatva is read from its titles. A call rings on top, through do not disturb, till it's handled; a stray click never answers or ends it.
- **One card per app** for ordinary notifications: the newest in full, older ones as a line each, so a burst takes one place.
- **Keys:** the newest card (calls first) has the focus; `akashvani key` (D-Bus `Key`) runs its main action, its numbered buttons, dismisses it, moves the focus. The desktop binds them (Vayu: Super+Ctrl+Enter, 1-3, Backspace, Tab). Popups never take keyboard focus themselves.
- **Local actions** (`akv:`): Copy code for a one-time code, Show them for the do not disturb summary; never sent to the app.
- **The theme decides:** only named colours in `style.css`; varna's `vyom.css` adds the glass (kept mostly solid so text reads over anything, light themes too), the desktop's fonts and the corner radius.

## Consequences

- Volume and brightness, a CI failure and a phone call are told apart at a glance; a flood stays one card.
- Answering a call, copying a login code or opening a download needs one key.
- The card's look follows `varna` (theme panel) without akashvani knowing about it; without varna, Vyom's palette and `monospace` stand in.
- More code in `toast.py` (slots instead of one card per notification); `akashvani list` still shows every notification separately.
