# 3. Use mako's history and modes

**Status:** Superseded by [0005](0005-be-the-notification-server.md)  
**Date:** 2026-10-19

## Context

The notification daemon owns notifications; a second store would disagree with it.

## Decision

akashvani reads `makoctl list` / `history`, invokes actions through makoctl, and implements do not disturb as a mako mode; every command is configurable for other daemons.

## Consequences

- Works out of the box with mako.
- Other daemons work through settings.
