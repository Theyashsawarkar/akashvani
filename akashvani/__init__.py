"""akashvani (आकाशवाणी, "notice"): notifications for Vyom, over mako.

What's on screen now (with the actions it offers, and dismiss), then the
history, grouped by app, newest first. The preview shows the whole
message. The switch at the top is do not disturb.
"""
import json
import os

from gi.repository import Gio, GLib, Gtk

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

# keybind: Vyom/notifications | Enter | Run the notification's default action, or copy its text
# keybind: Vyom/notifications | Ctrl+C | Copy the notification's text
# keybind: Vyom/notifications | Ctrl+Backspace | Dismiss the on-screen notification
# keybind: Vyom/notifications | Ctrl+N | Turn do not disturb on or off


def mako(*args):
    code, out = util.run(["makoctl", *args], timeout=5)
    if code:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    if isinstance(data, dict):  # older mako: {"data": [[...]]}
        data = (data.get("data") or [[]])[0]
    return data


def icon_of(n):
    ic = n.get("app_icon") or ""
    if ic.startswith("/") and os.path.exists(ic):
        return Gio.FileIcon.new(Gio.File.new_for_path(ic))
    if ic:
        return Gio.ThemedIcon.new(ic)
    return "\U000f009a"


class Plugin(Base):
    name, title, icon, color = "akashvani", "Notifications", "\U000f009a", "red"
    placeholder = "Search notifications…"
    preview = True
    preview_width = 320
    hints = [Hint("Enter", "action / copy"), Hint("Ctrl+Backspace", "dismiss"), Hint("Ctrl+N", "do not disturb")]
    empty_text = "No notifications"

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.switch = None

    # do not disturb: makoctl's "do-not-disturb" mode, or your commands
    def dnd_on(self):
        if self.conf.get("dnd_status"):
            out = util.run(self.conf["dnd_status"])[1]
            import re
            return re.search(self.conf.get("dnd_on_when", "^dnd$"), out, re.M) is not None
        return "do-not-disturb" in util.run(["makoctl", "mode"])[1].split()

    def set_dnd(self, on):
        if self.conf.get("dnd_on") and self.conf.get("dnd_off"):
            util.run(self.conf["dnd_on" if on else "dnd_off"])
        else:
            util.run(["makoctl", "mode", "-a" if on else "-r", "do-not-disturb"])

    def header_extra(self):
        box = Gtk.Box(spacing=8)
        box.append(ui.label("Do not disturb", "p-meta", valign=Gtk.Align.CENTER))
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.set_can_focus(False)
        self.handler = self.switch.connect("state-set", lambda _s, on: (self.background(lambda: self.set_dnd(on)), False)[1])
        box.append(self.switch)
        return box

    def opened(self, args):
        super().opened(args)
        on = self.dnd_on()
        if self.switch:
            self.switch.handler_block(self.handler)
            self.switch.set_active(on)
            self.switch.handler_unblock(self.handler)

    def search(self, q):
        live = mako("list", "-j")
        hist = mako("history", "-j")
        match = lambda n: not q or util.fuzzy(q, f"{n.get('app_name', '')} {n.get('summary', '')} {n.get('body', '')}") is not None
        rows = []
        live = [n for n in live if match(n)]
        if live:
            rows.append(Section("On screen"))
            rows += [self.row(n, True) for n in live]
        groups = {}
        for n in hist:
            if match(n):
                groups.setdefault(n.get("app_name") or "Other", []).append(n)
        for app, items in groups.items():   # history is newest first already
            rows.append(Section(f"{app} · {len(items)}" if len(items) > 1 else app))
            rows += [self.row(n, False) for n in items[:30]]
        return rows

    def row(self, n, live):
        summary = n.get("summary") or n.get("app_name") or "(no title)"
        body = " ".join((n.get("body") or "").split())
        urgent = n.get("urgency") == "critical"
        acts = n.get("actions") or {}
        return Row(summary, body, icon=icon_of(n), color="red" if urgent else "gray",
                   meta=f"{len(acts)} action{'s' if len(acts) != 1 else ''}" if live and acts else "",
                   badge="urgent" if urgent else "", badge_color="red", data={"n": n, "live": live})

    def build_preview(self, row):
        n, live = row.data["n"], row.data["live"]
        parts = [ui.meta(f"{n.get('app_name', '')}{' · on screen' if live else ''}"),
                 ui.title(n.get("summary") or "(no title)")]
        if n.get("body"):
            parts.append(ui.body(GLib.markup_escape_text(n["body"])))
        btns = []
        acts = n.get("actions") or {}
        if live:
            for key, label in list(acts.items())[:4]:
                btns.append((label or key, lambda k=key: self.invoke(n, k), "primary" if key == "default" else ""))
            btns.append(("Dismiss", lambda: self.dismiss(n), "danger"))
        btns.append(("Copy", lambda: self.copy(n)))
        box = ui.vbox(spacing=6)
        for spec in btns:
            box.append(ui.button(*spec))
        parts.append(box)
        return ui.vbox(*parts, spacing=12)

    def invoke(self, n, key):
        util.run(["makoctl", "invoke", "-n", str(n["id"]), key])
        self.close()

    def dismiss(self, n):
        util.run(["makoctl", "dismiss", "-n", str(n["id"])])
        self.refresh()

    def copy(self, n):
        util.copy("\n".join(x for x in (n.get("summary"), n.get("body")) if x))
        self.set_status("copied")

    def activate(self, row, mods):
        n, live = row.data["n"], row.data["live"]
        acts = n.get("actions") or {}
        if live and "default" in acts:
            self.invoke(n, "default")
            return False
        self.copy(n)
        return False

    def key(self, name, row, mods):
        if "ctrl" not in mods:
            return False
        if name == "n":
            on = not self.dnd_on()
            self.set_dnd(on)
            self.switch.set_active(on)
            return True
        if row is None:
            return False
        if name == "c":
            self.copy(row.data["n"])
        elif name == "BackSpace" and row.data["live"]:
            self.dismiss(row.data["n"])
        else:
            return False
        return True
