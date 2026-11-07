"""akashvani (आकाशवाणी, "notice"): notifications for Vyom, over mako.

What's on screen now (urgent first, with the actions it offers, and
dismiss), then the history: each app's notifications stacked into one row
with a count (Enter opens the stack), under Earlier today / Yesterday /
Older. Every row has a time. The preview shows the whole message and its
actions as buttons (Alt+1..9). Do not disturb in the header: for an hour,
till tomorrow morning or till you turn it off; a systemd timer (or a
detached sleep) turns it off again, so it works with the panel closed.

mako keeps no times, so akashvani notes them itself: it watches the
session bus for Notify calls (a D-Bus monitor; only the app, the summary
and the time are kept) and matches them to mako's ids; a notification it
didn't see arrive gets the time it was first listed.
"""
import datetime
import json
import os
import re
import shutil
import threading
import time

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

# keybind: Vyom/notifications | Enter | Run the notification's default action (or open an app's stack, or copy it)
# keybind: Vyom/notifications | Alt+1..9 | Run that numbered action of the notification
# keybind: Vyom/notifications | Ctrl+C | Copy the notification's text
# keybind: Vyom/notifications | Delete | Close the on-screen notification (dismiss it)
# keybind: Vyom/notifications | Ctrl+Backspace | Close every notification on screen (dismiss all)
# keybind: Vyom/notifications | Ctrl+N | Cycle do not disturb (off, 1 hour, till tomorrow, till you turn it off)

TIMES = "akashvani-times"
DND = "akashvani-dnd"
UNIT = "akashvani-dnd-off"
DND_MODES = [("off", "Off"), ("hour", "1 h"), ("tomorrow", "Till tomorrow"), ("on", "Till off")]


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
    return data if isinstance(data, list) else []


THEME = None   # the display's icon theme (set on the main loop; GTK 4's lookups are thread-safe)


def icon_of(n):
    """The app's icon if the icon theme has it, else a bell glyph."""
    ic = n.get("app_icon") or ""
    if ic.startswith("file://"):
        ic = ic[7:]
    if ic.startswith("/") and os.path.exists(ic):
        return Gio.FileIcon.new(Gio.File.new_for_path(ic))
    for name in (ic, n.get("desktop_entry") or "", (n.get("app_name") or "").lower()):
        if name and not name.startswith("/") and THEME is not None and THEME.has_icon(name):
            return Gio.ThemedIcon.new(name)
    return "\U000f009a"


def key_of(app, summary):
    return f"{app}\x00{summary}"


def when(t, now=None):
    """A short time: "now", "2 min", "09:41", "Yesterday 18:02", "Tue 09:41", "3 Nov"."""
    if not t:
        return ""
    now = now or time.time()
    d = now - t
    if d < 60:
        return "now"
    if d < 3600:
        return f"{int(d // 60)} min"
    a, b = datetime.datetime.fromtimestamp(t), datetime.datetime.fromtimestamp(now)
    days = (b.date() - a.date()).days
    if days == 0:
        return a.strftime("%H:%M")
    if days == 1:
        return "Yesterday " + a.strftime("%H:%M")
    if days < 7:
        return a.strftime("%a %H:%M")
    return f"{a.day} {a.strftime('%b')}"


def day_of(t, now=None):
    """Which section a time belongs to."""
    if not t:
        return "Earlier"
    days = (datetime.date.fromtimestamp(now or time.time()) - datetime.date.fromtimestamp(t)).days
    return "Earlier today" if days <= 0 else "Yesterday" if days == 1 else "Older"


class Watch:
    """Notes when each notification arrives: a monitor on the session bus
    for Notify calls. Lives as long as the daemon (plugins are made once)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.seen = []        # [(key, time)], oldest first, not yet matched to an id
        self.ok = False
        try:
            addr = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            self.conn = Gio.DBusConnection.new_for_address_sync(
                addr, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                None, None)
            self.conn.add_filter(self.filter)
            self.conn.call(
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus.Monitoring", "BecomeMonitor",
                GLib.Variant("(asu)", (["type='method_call',interface='org.freedesktop.Notifications',member='Notify'"], 0)),
                None, Gio.DBusCallFlags.NONE, 3000, None, self.started)
        except GLib.Error as e:
            util.log.debug("akashvani: no D-Bus monitor (%s); times are when first listed", e.message)

    def started(self, conn, res):
        try:
            conn.call_finish(res)
            self.ok = True
        except GLib.Error as e:
            util.log.debug("akashvani: BecomeMonitor refused (%s)", e.message)

    def filter(self, _conn, msg, _incoming):
        if msg.get_member() != "Notify" or msg.get_interface() != "org.freedesktop.Notifications":
            return msg
        try:
            body = msg.get_body().unpack()
            with self.lock:
                self.seen.append((key_of(body[0], body[3]), time.time()))
                del self.seen[:-200]
        except (AttributeError, IndexError, TypeError):
            pass
        return None

    def take(self, key):
        """The oldest unmatched arrival time of this app + summary."""
        with self.lock:
            for i, (k, t) in enumerate(self.seen):
                if k == key:
                    del self.seen[i]
                    return t
        return None


class Plugin(Base):
    name, title, icon, color = "akashvani", "Notifications", "\U000f009a", "red"
    placeholder = "Search notifications…"
    preview = True
    preview_width = 340
    hints = [Hint("Enter", "default action"), Hint("Alt+1..9", "actions"), Hint("Del", "dismiss"),
             Hint("Ctrl+N", "do not disturb")]
    empty_text = "No notifications"

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.dnd_box = None
        self.today_chip = None
        self.open_stacks = set()     # apps whose stack is open
        self.dnd = ("off", 0)        # (mode, until)
        self.held = 0
        self.today = 0
        self.times_lock = threading.Lock()
        self.watch = Watch()
        global THEME
        try:
            THEME = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        except TypeError:
            THEME = None

    # --------------------------------------------------------------- do not disturb
    def dnd_on(self):
        if self.conf.get("dnd_status"):
            out = util.run(self.conf["dnd_status"])[1]
            return re.search(self.conf.get("dnd_on_when", "^dnd$"), out, re.M) is not None
        return "do-not-disturb" in util.run(["makoctl", "mode"])[1].split()

    def off_command(self):
        """The command that turns do not disturb off, as argv (for a timer)."""
        if self.conf.get("dnd_on") and self.conf.get("dnd_off"):
            return ["/bin/sh", "-c", util.expand(self.conf["dnd_off"])]
        return [shutil.which("makoctl") or "makoctl", "mode", "-r", "do-not-disturb"]

    def switch_dnd(self, on):
        if self.conf.get("dnd_on") and self.conf.get("dnd_off"):
            util.run(self.conf["dnd_on" if on else "dnd_off"])
        else:
            util.run(["makoctl", "mode", "-a" if on else "-r", "do-not-disturb"])

    def read_dnd(self):
        """(mode, until) from the real state: a saved end time only counts
        while do not disturb is really on."""
        if not self.dnd_on():
            return ("off", 0)
        st = util.load_state(DND, {})
        until = st.get("until") or 0
        if st.get("mode") in ("hour", "tomorrow") and until > time.time():
            return (st["mode"], until)
        return ("on", 0)

    def morning(self):
        """Tomorrow morning (dnd_morning, default 08:00); before 05:00 that's today's."""
        hh, mm = (int(x) for x in str(self.conf.get("dnd_morning", "08:00")).split(":")[:2])
        now = datetime.datetime.now()
        day = now.date() if now.hour < 5 else now.date() + datetime.timedelta(days=1)
        return datetime.datetime.combine(day, datetime.time(hh, mm)).timestamp()

    def set_dnd(self, mode):
        """Runs in the background: turn it on/off and (re)set the timer."""
        was_on = self.dnd_on()
        if shutil.which("systemctl"):
            util.run(["systemctl", "--user", "stop", f"{UNIT}.timer"], timeout=5)
        until = 0
        if mode == "off":
            if was_on:
                self.switch_dnd(False)
        else:
            if not was_on:
                self.switch_dnd(True)
            if mode in ("hour", "tomorrow"):
                until = time.time() + 3600 if mode == "hour" else self.morning()
                self.schedule_off(int(until - time.time()))
        st = util.load_state(DND, {})
        util.save_state(DND, {"mode": mode, "until": until,
                              "since": st.get("since") if was_on and mode != "off" else (time.time() if mode != "off" else 0)})
        return mode

    def schedule_off(self, seconds):
        """Turn do not disturb off in `seconds`, without the panel: a systemd
        user timer, else a detached sleep."""
        cmd = self.off_command()
        if shutil.which("systemd-run"):
            code, _ = util.run(["systemd-run", "--user", "--quiet", "--collect", f"--unit={UNIT}",
                                f"--on-active={max(1, seconds)}s", *cmd], timeout=10)
            if code == 0:
                return
        util.spawn(["/bin/sh", "-c", f"sleep {max(1, seconds)}; exec \"$0\" \"$@\"", *cmd])

    def pick_dnd(self, mode):
        self.set_status("do not disturb: " + dict(DND_MODES)[mode].lower())
        self.background(lambda: self.set_dnd(mode), lambda _r: self.refresh())

    def header_extra(self):
        box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.today_chip = ui.chip("", "gray")
        self.today_chip.set_visible(False)
        box.append(self.today_chip)
        box.append(ui.label("\U000f009b", "glyph", "dnd-icon", valign=Gtk.Align.CENTER, tooltip_text="Do not disturb (Ctrl+N)"))
        self.dnd_box = Gtk.Box(valign=Gtk.Align.CENTER)
        box.append(self.dnd_box)
        self.show_dnd()
        return box

    def show_dnd(self):
        if self.dnd_box is None:
            return
        old = self.dnd_box.get_first_child()
        if old is not None:
            self.dnd_box.remove(old)
        seg = ui.segmented(DND_MODES, self.dnd[0], self.pick_dnd)
        seg.add_css_class("dnd")
        seg.set_tooltip_text("Do not disturb (Ctrl+N cycles)")
        child = seg.get_first_child()
        while child is not None:
            child.set_can_focus(False)
            child = child.get_next_sibling()
        self.dnd_box.append(seg)

    def build_strip(self):
        # (runs on the main loop after every search: the header follows too)
        if self.today_chip is not None:
            self.today_chip.set_label(f"{self.today} today")
            self.today_chip.set_visible(self.today > 0)
        self.show_dnd()
        mode, until = self.dnd
        if mode == "off":
            return None
        end = {"hour": f"until {time.strftime('%H:%M', time.localtime(until))}",
               "tomorrow": f"until {when_day(until)}"}.get(mode, "until you turn it off")
        held = f"holding {self.held} notification{'s' if self.held != 1 else ''}" if self.held else "nothing held yet"
        txt = ui.vbox(ui.hbox(ui.label("Do not disturb", "hero-title"), ui.chip("On", "yellow", "\U000f009b"), spacing=8),
                      ui.label(f"{end} · {held}", "hero-sub", xalign=0), spacing=4)
        txt.set_hexpand(True)
        return ui.hero(txt, ui.button("Turn off", lambda: self.pick_dnd("off"), key="Ctrl+N" if mode == "on" else ""),
                       color="yellow")

    def opened(self, args):
        super().opened(args)
        self.dnd = self.read_dnd()
        self.show_dnd()

    # --------------------------------------------------------------- times
    def stamp(self, notes):
        """Gives every notification a "t" (when it arrived), noted once per id."""
        with self.times_lock:
            st = util.load_state(TIMES, {})
            ids = {str(k): v for k, v in (st.get("ids") or {}).items()}
            known = {str(n.get("id")) for n in notes}
            first = "baseline" not in st
            baseline = st.get("baseline", max((n.get("id") or 0 for n in notes), default=0))
            changed = first
            for n in sorted(notes, key=lambda n: n.get("id") or 0):
                k = str(n.get("id"))
                if k not in ids:
                    t = self.watch.take(key_of(n.get("app_name") or "", n.get("summary") or ""))
                    if t is None:
                        # one from before akashvani watched: no time; a newer one: now
                        t = 0 if (n.get("id") or 0) <= baseline else time.time()
                    ids[k] = t
                    changed = True
                n["t"] = ids[k]
            if changed or len(ids) > len(known) + 50:
                util.save_state(TIMES, {"baseline": baseline, "ids": {k: v for k, v in ids.items() if k in known}})

    # --------------------------------------------------------------- search
    def search(self, q):
        live = mako("list", "-j")
        hist = mako("history", "-j")
        self.dnd = self.read_dnd()
        self.stamp(live + hist)
        now = time.time()
        since = util.load_state(DND, {}).get("since") or 0
        self.held = sum(1 for n in live + hist if self.dnd[0] != "off" and since and n["t"] >= since)
        today = datetime.date.today()
        self.today = sum(1 for n in live + hist if n["t"] and datetime.date.fromtimestamp(n["t"]) == today)

        def match(n):
            return not q or util.fuzzy(q, f"{n.get('app_name', '')} {n.get('summary', '')} {n.get('body', '')}") is not None
        rows = []
        live = sorted((n for n in live if match(n)), key=lambda n: (n.get("urgency") != "critical", -(n["t"] or 0)))
        if live:
            rows.append(Section("On screen now", len(live), "Ctrl+⌫ dismisses all" if len(live) > 1 else ""))
            rows += [self.row(n, True, now) for n in live]
        live_ids = {n.get("id") for n in live}
        hist = [n for n in hist if match(n) and n.get("id") not in live_ids]
        if q:   # searching: every match is its own row (a stack would hide what matched)
            stacks = [[n] for n in hist]
        else:
            by_app = {}
            for n in hist:   # newest first already
                by_app.setdefault(n.get("app_name") or "Other", []).append(n)
            stacks = list(by_app.values())
        stacks.sort(key=lambda s: -(max(n["t"] or 0 for n in s)))
        groups = {}
        for s in stacks:
            groups.setdefault(day_of(s[0]["t"], now), []).append(s)
        for title in ("Earlier today", "Yesterday", "Older", "Earlier"):
            if title not in groups:
                continue
            got = groups[title]
            rows.append(Section(title, sum(len(s) for s in got)))
            for s in got:
                app = s[0].get("app_name") or "Other"
                is_open = app in self.open_stacks and len(s) > 1
                rows.append(self.row(s[0], False, now, stack=s, opened=is_open))
                if is_open:
                    rows += [self.row(n, False, now, child=True) for n in s[1:30]]
        return rows

    def row(self, n, live, now, stack=None, opened=False, child=False):
        app = n.get("app_name") or ""
        summary = n.get("summary") or app or "(no title)"
        body = " ".join(util.strip_markup(n.get("body") or "").split())
        urgent = n.get("urgency") == "critical"
        chips = []
        if urgent:
            chips.append(("Urgent", "red"))
        if stack and len(stack) > 1:
            chips.append((("▾ " if opened else "") + str(len(stack)), "gray"))
        if stack and len(stack) > 1:
            title, sub = app or summary, " · ".join(x for x in (summary, body) if x)
        elif child:
            title, sub = "↳ " + summary, body
        else:
            title = summary
            sub = " · ".join(x for x in (app if app.lower() not in summary.lower() else "", body) if x)
        return Row(title, sub, icon=icon_of(n), color="red" if urgent else "gray", meta=when(n["t"], now),
                   chips=chips, data={"n": n, "live": live, "stack": stack or [n], "app": app})

    # --------------------------------------------------------------- preview
    def actions(self, n, live):
        """[(key, label)] the notification offers, without the default one."""
        if not live:
            return []
        return [(k, v or k) for k, v in (n.get("actions") or {}).items() if k != "default"][:9]

    def build_preview(self, row):
        n, live, stack = row.data["n"], row.data["live"], row.data["stack"]
        where = " · ".join(x for x in (n.get("app_name"), "on screen" if live else "", when(n["t"])) if x)
        head = ui.hbox(ui.meta(where), spacing=8)
        if n.get("urgency") == "critical":
            head.append(ui.chip("Urgent", "red", "\U000f0026"))
        parts = [head, ui.title(n.get("summary") or "(no title)")]
        if n.get("body"):
            parts.append(ui.body(GLib.markup_escape_text(util.strip_markup(n["body"]))))
        btns = ui.vbox(spacing=8)
        acts = n.get("actions") or {}
        if live and "default" in acts:
            btns.append(ui.button(acts["default"] or "Open", lambda: self.invoke(n, "default"), "primary",
                                  "\U000f03cc", "Enter"))
        for i, (k, label) in enumerate(self.actions(n, live), 1):
            btns.append(ui.button(label, lambda k=k: self.invoke(n, k), icon="\U000f040a", key=f"Alt+{i}"))
        btns.append(ui.button("Copy", lambda: self.copy(n), icon="\U000f018f", key="Ctrl+C"))
        if live:
            btns.append(ui.button("Dismiss", lambda: self.dismiss(n), "danger", "\U000f0156", "Del"))
        for b in _children(btns):
            spread(b)
        parts.append(btns)
        if len(stack) > 1 and row.data["n"] is stack[0]:
            others = ui.vbox(ui.section(f"Also from {n.get('app_name') or 'this app'}", len(stack) - 1,
                                        "Enter opens" if row.data["app"] not in self.open_stacks else "Enter folds"),
                             spacing=4)
            for o in stack[1:6]:
                line = ui.hbox(ui.label(when(o["t"]) or "·", "row-meta", width_chars=6, xalign=0),
                               ui.label(o.get("summary") or "(no title)", "p-body", xalign=0, hexpand=True,
                                        ellipsize=Pango.EllipsizeMode.END), spacing=8)
                others.append(line)
            if len(stack) > 6:
                others.append(ui.meta(f"and {len(stack) - 6} more"))
            parts.append(others)
        return ui.vbox(*parts, spacing=12)

    # --------------------------------------------------------------- actions
    def invoke(self, n, key):
        util.run(["makoctl", "invoke", "-n", str(n["id"]), key])
        self.close()

    def dismiss(self, n):
        util.run(["makoctl", "dismiss", "-n", str(n["id"])])
        self.set_status("dismissed")
        self.panel.refresh_now(keep_selection=True)

    def copy(self, n):
        util.copy("\n".join(x for x in (n.get("summary"), util.strip_markup(n.get("body") or "")) if x))
        self.set_status("copied")

    def activate(self, row, mods):
        n, live, stack, app = row.data["n"], row.data["live"], row.data["stack"], row.data["app"]
        acts = n.get("actions") or {}
        if live and "default" in acts:
            self.invoke(n, "default")
        elif len(stack) > 1:
            self.open_stacks ^= {app}
            self.panel.refresh_now(keep_selection=True)
        else:
            self.copy(n)
        return False

    def key(self, name, row, mods):
        if mods == {"ctrl"} and name == "n":
            keys = [k for k, _ in DND_MODES]
            self.pick_dnd(keys[(keys.index(self.dnd[0]) + 1) % len(keys)])
            return True
        if mods == {"ctrl"} and name == "BackSpace":
            util.run(["makoctl", "dismiss", "-a"])
            self.set_status("dismissed everything on screen")
            self.refresh()
            return True
        if row is None:
            return False
        n = row.data["n"]
        if mods == {"alt"} and len(name) == 1 and name in "123456789":
            acts = self.actions(n, row.data["live"])
            i = int(name) - 1
            if i < len(acts):
                self.invoke(n, acts[i][0])
            return True
        if mods == {"ctrl"} and name == "c":
            self.copy(n)
            return True
        if name in ("Delete", "KP_Delete") and not mods and row.data["live"]:
            e = self.panel.entry
            if e.get_position() < len(e.get_text()):
                return False   # deleting text in the search box
            self.dismiss(n)
            return True
        return False


def when_day(t):
    a = datetime.datetime.fromtimestamp(t)
    return ("tomorrow " if a.date() > datetime.date.today() else "") + a.strftime("%H:%M")


def _children(box):
    c = box.get_first_child()
    while c is not None:
        yield c
        c = c.get_next_sibling()


def spread(button):
    """A full-width button: icon and text on the left, its key on the right."""
    inner = button.get_child()
    kids = list(_children(inner))
    for k in kids:
        if k.has_css_class("keycap"):
            k.set_halign(Gtk.Align.END)
            k.set_hexpand(True)
