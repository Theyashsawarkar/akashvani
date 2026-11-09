"""akashvani's vim keys, as data. The modes, counts, sequences, which-key
strip, help (?) and palette (Space Space) are Vyom's (vyom/keys.py,
vyom/modal.py; Vyom ADR 0008); this file is only what akashvani adds. Space
groups follow Vayu's shared letters: y copy, d delete (dismiss), f filter,
u toggles; n (do not disturb) and x (a notification's own actions) are
akashvani's.

An action "verb:arg" runs Plugin.v_<verb>(count, arg) in akashvani/__init__.py,
or Vyom's own (activate, insert, moved...).
"""
from vyom.keys import Bind

B = Bind

GROUPS = {" n": "do not disturb", " x": "action"}

NORMAL = [
    B("<CR>", "activate", "Run the notification's default action (or open an app's stack, or copy it)"),
    B("h", "fold:close", "Fold the app's stack"),
    B("l", "fold:open", "Open the app's stack"),
    B("dd", "dismiss", "Dismiss the on-screen notification (it stays in the history)"),
    B("<Del>", "dismiss", "", hidden=True),
    B("u", "restore", "Bring back the last dismissed notification"),
    B("yy", "copy", "Copy the notification's text"),
    B("<C-c>", "copy", "", hidden=True),
    B("<C-BS>", "moved:Space d a dismisses all", "", hidden=True),
]

BOTH = [
    ("Alt+1..9", "Run that numbered action of the notification"),
    ("Ctrl+N", "Cycle do not disturb (off, 1 hour, till tomorrow, till you turn it off)"),
]

ACTIONS = [B(f" x{i}", f"action:{i}", f"Run the notification's action {i}") for i in range(1, 10)]

LEADER = [
    B(" nn", "dnd:next", "Cycle do not disturb (off, 1 hour, till tomorrow, till you turn it off)"),
    B(" no", "dnd:off", "Turn do not disturb off"),
    B(" nh", "dnd:hour", "Turn do not disturb on for an hour"),
    B(" nt", "dnd:tomorrow", "Turn do not disturb on till tomorrow morning"),
    B(" na", "dnd:on", "Turn do not disturb on till you turn it off"),
    B(" dd", "dismiss", "Dismiss the on-screen notification"),
    B(" da", "dismissall", "Dismiss every notification on screen (asks first)"),
    B(" fl", "filter:live", "Show only what's on screen now"),
    B(" fh", "filter:history", "Show only the history"),
    B(" fa", "filter:app", "Show only the selected notification's app"),
    B(" fc", "filter:", "Clear the filter (show everything)"),
    B(" yy", "copy", "Copy the notification's text"),
    B(" yb", "copy:body", "Copy the notification's body only"),
]


def keys(tab):
    return NORMAL + ACTIONS + LEADER


SECTIONS = [
    ("akashvani", "normal", "Normal mode (akashvani opens in it)", NORMAL),
    ("akashvani", "any", "Both modes", BOTH),
    ("akashvani leader", "normal", "Leader (Space)", [("Space x 1..9", "Run that numbered action of the notification")]
     + LEADER),
]
