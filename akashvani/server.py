"""akashvani's notification server: it owns org.freedesktop.Notifications on
the session bus (the freedesktop Desktop Notifications spec, 1.2), inside
the Vyom daemon, so no extra process runs.

  Store    what's on screen now (live), the history (closed ones, newest
           first, with times; saved across restarts), modes (do not disturb,
           silent), rules.
  Server   the spec's methods and signals, plus dev.vayu.Akashvani at
           /dev/vayu/Akashvani for the `akashvani` command (list, history,
           dismiss, invoke, restore, mode, reload) and the panel.
  toast.py draws the popups.

The name is requested with a place in the queue: while another daemon (mako,
dunst) holds it, akashvani waits and the panel reads that daemon through
makoctl; the moment it exits, akashvani takes over.
"""
import json
import logging
import os
import re
import shutil
import threading
import time

from gi.repository import Gio, GLib
from vyom import util

log = logging.getLogger("vyom.akashvani")

NAME = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"
CTL_PATH = "/dev/vayu/Akashvani"
CTL_IFACE = "dev.vayu.Akashvani"
SPEC_VERSION = "1.2"

HISTORY = "akashvani-history"
MODES = "akashvani-modes"

# NotificationClosed reasons
EXPIRED, DISMISSED, CLOSED, UNDEFINED = 1, 2, 3, 4

URGENCY = {0: "low", 1: "normal", 2: "critical"}
DND_MODES = {"dnd", "do-not-disturb"}
SILENT_MODES = {"silent"} | DND_MODES

XML = """
<node>
  <interface name="org.freedesktop.Notifications">
    <method name="Notify">
      <arg type="s" name="app_name" direction="in"/>
      <arg type="u" name="replaces_id" direction="in"/>
      <arg type="s" name="app_icon" direction="in"/>
      <arg type="s" name="summary" direction="in"/>
      <arg type="s" name="body" direction="in"/>
      <arg type="as" name="actions" direction="in"/>
      <arg type="a{sv}" name="hints" direction="in"/>
      <arg type="i" name="expire_timeout" direction="in"/>
      <arg type="u" name="id" direction="out"/>
    </method>
    <method name="CloseNotification"><arg type="u" name="id" direction="in"/></method>
    <method name="GetCapabilities"><arg type="as" name="caps" direction="out"/></method>
    <method name="GetServerInformation">
      <arg type="s" name="name" direction="out"/>
      <arg type="s" name="vendor" direction="out"/>
      <arg type="s" name="version" direction="out"/>
      <arg type="s" name="spec_version" direction="out"/>
    </method>
    <signal name="NotificationClosed"><arg type="u" name="id"/><arg type="u" name="reason"/></signal>
    <signal name="ActionInvoked"><arg type="u" name="id"/><arg type="s" name="action_key"/></signal>
  </interface>
  <interface name="dev.vayu.Akashvani">
    <method name="List"><arg type="s" name="json" direction="out"/></method>
    <method name="History"><arg type="s" name="json" direction="out"/></method>
    <method name="Dismiss">
      <arg type="u" name="id" direction="in"/>
      <arg type="b" name="all" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="Restore"><arg type="b" name="ok" direction="out"/></method>
    <method name="Invoke">
      <arg type="u" name="id" direction="in"/>
      <arg type="s" name="action" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="Modes"><arg type="as" name="modes" direction="out"/></method>
    <method name="SetModes">
      <arg type="as" name="modes" direction="in"/>
      <arg type="as" name="now" direction="out"/>
    </method>
    <method name="ClearHistory"/>
    <method name="Reload"/>
    <method name="Status"><arg type="s" name="json" direction="out"/></method>
    <signal name="Changed"/>
  </interface>
</node>
"""

# The keys a notification has in `list -j` / `history -j` (makoctl's shape,
# so scripts written for mako keep working), plus ours.
PUBLIC = ("id", "app_name", "app_icon", "category", "desktop_entry", "summary", "body", "urgency", "actions",
          "t", "value", "image_path", "resident", "transient")


def _str(v):
    return v if isinstance(v, str) else ""


class Note(dict):
    """A notification: a dict in makoctl's JSON shape, plus what only the
    screen needs (the image's texture, the timer)."""
    __slots__ = ("hidden", "left", "rule", "started", "sync", "texture", "timer")

    def __init__(self, **kw):
        super().__init__(**kw)
        self.texture = None    # Gdk.Texture from image-data (never saved)
        self.timer = 0         # GLib source id of the expiry
        self.left = 0          # ms left when the timer was paused (hover)
        self.started = 0.0
        self.rule = {}         # what the rules decided (timeout, hidden, sound, history...)
        self.hidden = False    # held: do not disturb or a rule (no popup)
        self.sync = ""         # x-canonical-private-synchronous / x-dunst-stack-tag

    def public(self):
        return {k: self.get(k) for k in PUBLIC if k in self}


class Server:
    """The daemon half of akashvani. Everything runs on the GTK main loop;
    snapshot() is the one thing the panel's worker thread may call."""

    def __init__(self, plugin):
        self.plugin = plugin
        self.lock = threading.Lock()
        self.live = []           # [Note], oldest first (as they arrived)
        self.history = []        # [dict], newest first
        self.restorable = []     # [Note] dismissed by the user, newest last (restore)
        self.next_id = 1
        self.owned = False       # we hold the name
        self.conn = None
        self.listeners = []      # callables run after every change (the panel, the popups)
        self.toast = None
        self.modes = set(util.load_state(MODES, {}).get("modes") or ["default"])
        self.dnd_timer = 0
        self._save_src = 0
        self._load_history()
        self._start()

    # ------------------------------------------------------------- settings
    @property
    def conf(self):
        return self.plugin.conf

    def opt(self, key, default):
        v = self.conf.get(key, default)
        return default if v is None else v

    # ------------------------------------------------------------- the bus
    def _start(self):
        try:
            self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            node = Gio.DBusNodeInfo.new_for_xml(XML)
            for iface in node.interfaces:
                path = PATH if iface.name == NAME else CTL_PATH
                self.conn.register_object(path, iface, self._call, None, None)
        except GLib.Error as e:
            log.error("akashvani: no session bus (%s); not serving notifications", e.message)
            self.conn = None
            return
        # REPLACE takes the name from a daemon that allows it; otherwise we
        # queue, and get it as soon as that daemon exits.
        self.name_id = Gio.bus_own_name_on_connection(
            self.conn, NAME, Gio.BusNameOwnerFlags.REPLACE, self._acquired, self._lost)
        self._restore_dnd_timer()

    def _acquired(self, _conn, _name):
        self.owned = True
        log.info("akashvani: serving notifications (%s)", NAME)
        self.changed()

    def _lost(self, _conn, _name):
        was = self.owned
        self.owned = False
        if was:
            log.warning("akashvani: another daemon took %s; waiting for it to exit", NAME)
        else:
            log.info("akashvani: %s is held by another daemon (mako?); waiting in the queue", NAME)
        if self.toast:
            self.toast.clear()
        self.changed()

    def _emit(self, iface, signal, args):
        if self.conn is None:
            return
        try:
            self.conn.emit_signal(None, PATH if iface == NAME else CTL_PATH, iface, signal, args)
        except GLib.Error as e:
            log.debug("akashvani: emit %s failed: %s", signal, e.message)

    def _call(self, _conn, _sender, _path, iface, method, params, inv):
        try:
            out = self._dispatch(iface, method, params)
        except Exception as e:   # never leave a caller hanging
            log.exception("akashvani: %s.%s failed", iface, method)
            inv.return_dbus_error("org.freedesktop.DBus.Error.Failed", str(e))
            return
        inv.return_value(out)

    def _dispatch(self, iface, method, params):
        if iface == NAME:
            if method == "Notify":
                return GLib.Variant("(u)", (self.notify(params),))
            if method == "CloseNotification":
                self.close(params.unpack()[0], CLOSED)
                return None
            if method == "GetCapabilities":
                caps = ["body", "body-markup", "body-hyperlinks", "actions", "icon-static", "persistence",
                        "x-canonical-private-synchronous", "x-dunst-stack-tag", "sound"]
                return GLib.Variant("(as)", (caps,))
            if method == "GetServerInformation":
                return GLib.Variant("(ssss)", ("akashvani", "Vayu", self.plugin_version(), SPEC_VERSION))
        a = params.unpack() if params is not None else ()
        if method == "List":
            return GLib.Variant("(s)", (json.dumps(self.snapshot()[0]),))
        if method == "History":
            return GLib.Variant("(s)", (json.dumps(self.snapshot()[1]),))
        if method == "Dismiss":
            return GLib.Variant("(b)", (self.dismiss(a[0], every=a[1]),))
        if method == "Restore":
            return GLib.Variant("(b)", (self.restore(),))
        if method == "Invoke":
            return GLib.Variant("(b)", (self.invoke(a[0], a[1] or "default"),))
        if method == "Modes":
            return GLib.Variant("(as)", (sorted(self.modes),))
        if method == "SetModes":
            self.set_modes(a[0])
            return GLib.Variant("(as)", (sorted(self.modes),))
        if method == "ClearHistory":
            self.clear_history()
            return None
        if method == "Reload":
            self.reload()
            return None
        if method == "Status":
            return GLib.Variant("(s)", (json.dumps(self.status()),))
        raise ValueError(f"unknown method {method}")

    def plugin_version(self):
        try:
            import tomllib
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            with open(os.path.join(here, "plugin.toml"), "rb") as f:
                return tomllib.load(f).get("version", "")
        except (OSError, ValueError):
            return ""

    # ------------------------------------------------------------- Notify
    def notify(self, params):
        app, replaces, icon, summary, body, actions = (params.get_child_value(i).unpack() for i in range(6))
        hv = params.get_child_value(6)
        timeout = params.get_child_value(7).get_int32()
        hints = {}
        for i in range(hv.n_children()):
            entry = hv.get_child_value(i)
            k = entry.get_child_value(0).get_string()
            v = entry.get_child_value(1).get_variant()
            if k in ("image-data", "image_data", "icon_data"):
                hints["__image"] = v
            else:
                try:
                    hints[k] = v.unpack()
                except (TypeError, ValueError):
                    pass

        urg = hints.get("urgency")
        urgency = URGENCY.get(urg if isinstance(urg, int) else 1, "normal")
        acts = {}
        for i in range(0, len(actions) - 1, 2):
            acts[actions[i]] = actions[i + 1]
        value = hints.get("value")
        n = Note(id=0, app_name=app or "", app_icon=icon or None, summary=summary or "", body=body or None,
                 urgency=urgency, category=_str(hints.get("category")) or None,
                 desktop_entry=_str(hints.get("desktop-entry")) or None, actions=acts, t=time.time())
        if isinstance(value, int):
            n["value"] = max(0, min(100, value))
        ip = _str(hints.get("image-path") or hints.get("image_path"))
        if ip:
            n["image_path"] = ip.removeprefix("file://")
        if hints.get("resident"):
            n["resident"] = True
        if hints.get("transient"):
            n["transient"] = True
        n.sync = _str(hints.get("x-canonical-private-synchronous") or hints.get("x-dunst-stack-tag"))
        if "__image" in hints:
            n.texture = image_texture(hints["__image"])

        # replaces_id, or the same synchronous tag (volume, brightness): the
        # one on screen changes in place and keeps its id.
        old = None
        if replaces:
            old = self.find(replaces)
        if old is None and n.sync:
            old = next((x for x in self.live if x.sync == n.sync and x["app_name"] == n["app_name"]), None)
        if old is not None:
            n["id"] = old["id"]
            n["t"] = time.time()
        else:
            n["id"] = self.new_id()

        n.rule = self.rules_for(n)
        if n.rule.get("ignore"):
            return n["id"]
        if "urgency" in n.rule:
            n["urgency"] = n.rule["urgency"]
        n.hidden = bool(n.rule.get("hidden")) or (self.dnd() and n["urgency"] != "critical"
                                                    and not n.rule.get("show_in_dnd"))
        ms = self.timeout_for(n, timeout)

        with self.lock:
            if old is not None:
                self._stop_timer(old)
                self.live[self.live.index(old)] = n
            else:
                self.live.append(n)
        self._arm(n, ms)
        if old is None and not n.hidden:
            self.sound(n, hints)
        if self.toast and not n.hidden:
            self.toast.show(n, replace=old)
        self.changed()
        return n["id"]

    def new_id(self):
        i = self.next_id
        self.next_id = 1 if i >= 0xFFFFFFF0 else i + 1
        return i

    def find(self, nid):
        return next((x for x in self.live if x["id"] == nid), None)

    def timeout_for(self, n, asked):
        """ms until it expires (0: never). A rule wins; then what the app
        asked for (unless ignore_timeout); then the default by urgency."""
        if "timeout" in n.rule:
            return max(0, int(n.rule["timeout"]))
        if asked > 0 and not self.opt("ignore_timeout", False):
            return asked
        if asked == 0 and not self.opt("ignore_timeout", False):
            return 0
        by = {"low": self.opt("timeout_low", 3000), "normal": self.opt("timeout", 5000),
              "critical": self.opt("timeout_critical", 0)}
        ms = by[n["urgency"]]
        if n["actions"] and n["urgency"] != "critical":
            ms = max(ms, self.opt("timeout_actions", 8000))
        return max(0, int(ms))

    # ------------------------------------------------------------- rules
    def rules_for(self, n):
        """[[plugin.akashvani.rules]]: every rule whose match keys all fit,
        in order (a later one wins)."""
        out = {}
        for r in self.conf.get("rules") or []:
            if isinstance(r, dict) and self._matches(r, n):
                out.update({k: v for k, v in r.items() if k not in MATCH_KEYS})
        return out

    def _matches(self, r, n):
        for k in MATCH_KEYS:
            if k not in r:
                continue
            want = r[k]
            if k == "mode":
                if want not in self.modes:
                    return False
            elif k == "actionable":
                if bool(n["actions"]) != bool(want):
                    return False
            elif k == "sync":
                if bool(n.sync) != bool(want):
                    return False
            else:
                field = {"app": "app_name"}.get(k, k)
                have = n.get(field) or ""
                if k == "urgency":
                    if have != want:
                        return False
                elif not re.search(str(want), str(have), re.IGNORECASE):
                    return False
        return True

    # ------------------------------------------------------------- timers
    def _arm(self, n, ms):
        n["timeout"] = ms
        if ms > 0:
            n.started = time.monotonic()
            n.left = ms
            n.timer = GLib.timeout_add(ms, self._expire, n)

    def _stop_timer(self, n):
        if n.timer:
            GLib.source_remove(n.timer)
            n.timer = 0

    def _expire(self, n):
        n.timer = 0
        self.close(n["id"], EXPIRED)
        return False

    def pause(self, n):
        """The pointer is on it: the clock stops."""
        if n.timer:
            n.left = max(500, n.left - (time.monotonic() - n.started) * 1000)
            self._stop_timer(n)

    def resume(self, n):
        if not n.timer and n.get("timeout", 0) > 0 and n in self.live:
            n.started = time.monotonic()
            n.timer = GLib.timeout_add(int(max(n.left, 1500)), self._expire, n)

    # ------------------------------------------------------------- closing
    def close(self, nid, reason):
        n = self.find(nid)
        if n is None:
            return False
        self._stop_timer(n)
        with self.lock:
            self.live.remove(n)
            if self._keeps(n):
                rec = n.public()
                rec["closed"] = time.time()
                self.history.insert(0, rec)
                del self.history[int(self.opt("history_max", 200)):]
        if reason == DISMISSED:
            self.restorable.append(n)
            del self.restorable[:-20]
        if self.toast:
            self.toast.remove(n)
        self._emit(NAME, "NotificationClosed", GLib.Variant("(uu)", (nid, reason)))
        self.save_soon()
        self.changed()
        return True

    def _keeps(self, n):
        """Goes to the history: not transient, not a volume/brightness slider
        (history_sync = true keeps those too), not ruled out."""
        if "history" in n.rule:
            return bool(n.rule["history"])
        if n.get("transient"):
            return False
        if n.sync and not self.opt("history_sync", False):
            return False
        return True

    def dismiss(self, nid=0, every=False):
        if every:
            ids = [n["id"] for n in list(self.live)]
            for i in ids:
                self.close(i, DISMISSED)
            return bool(ids)
        if not nid:
            shown = [n for n in self.live if not n.hidden]
            if not shown:
                return False
            nid = shown[-1]["id"]
        return self.close(nid, DISMISSED)

    def restore(self):
        while self.restorable:
            n = self.restorable.pop()
            with self.lock:
                self.history = [h for h in self.history if h.get("id") != n["id"]]
                n["t"] = n.get("t") or time.time()
                n.hidden = False
                self.live.append(n)
            self._arm(n, 0)    # brought back on purpose: it stays till you dismiss it
            if self.toast:
                self.toast.show(n)
            self.save_soon()
            self.changed()
            return True
        return False

    def invoke(self, nid, action="default"):
        n = self.find(nid) if nid else (self.live[-1] if self.live else None)
        if n is None or action not in n["actions"]:
            return False
        self._emit(NAME, "ActionInvoked", GLib.Variant("(us)", (n["id"], action)))
        if not n.get("resident"):
            self.close(n["id"], DISMISSED)
        return True

    def clear_history(self):
        with self.lock:
            self.history = []
        self.save_soon()
        self.changed()

    # ------------------------------------------------------------- modes
    def dnd(self):
        return bool(self.modes & DND_MODES)

    def set_modes(self, modes):
        new = {m for m in modes if m} or {"default"}
        if new == self.modes:
            return
        was_dnd = self.dnd()
        self.modes = new
        util.save_state(MODES, {"modes": sorted(new), "since": time.time() if self.dnd() else 0})
        if was_dnd and not self.dnd():
            # held ones that are still live now show
            for n in self.live:
                if n.hidden and not n.rule.get("hidden"):
                    n.hidden = False
                    if self.toast:
                        self.toast.show(n)
            self.cancel_dnd_timer()
        elif self.dnd() and not was_dnd and self.toast:
            for n in self.live:
                if n["urgency"] != "critical" and not n.rule.get("show_in_dnd"):
                    n.hidden = True
                    self.toast.remove(n)
        self._emit(CTL_IFACE, "Changed", None)
        self.changed()

    def add_mode(self, m):
        self.set_modes(self.modes - {"default"} | {m})

    def remove_mode(self, *ms):
        self.set_modes(self.modes - set(ms))

    def dnd_since(self):
        return util.load_state(MODES, {}).get("since") or 0

    def dnd_off_at(self, until):
        """Turn do not disturb off at `until` (0: never); kept across restarts."""
        self.cancel_dnd_timer()
        st = util.load_state(MODES, {})
        st["until"] = until
        util.save_state(MODES, st)
        if until:
            self.dnd_timer = GLib.timeout_add_seconds(max(1, int(until - time.time())), self._dnd_due)

    def cancel_dnd_timer(self):
        if self.dnd_timer:
            GLib.source_remove(self.dnd_timer)
            self.dnd_timer = 0

    def _dnd_due(self):
        self.dnd_timer = 0
        self.remove_mode(*DND_MODES)
        return False

    def _restore_dnd_timer(self):
        until = util.load_state(MODES, {}).get("until") or 0
        if until and self.dnd():
            if until <= time.time():
                self.remove_mode(*DND_MODES)
            else:
                self.dnd_timer = GLib.timeout_add_seconds(int(until - time.time()), self._dnd_due)

    # ------------------------------------------------------------- sound
    def sound(self, n, hints):
        if self.modes & SILENT_MODES or hints.get("suppress-sound"):
            return
        snd = n.rule.get("sound", None)
        if snd is False or snd == "":
            return
        snd = snd or _str(hints.get("sound-file")) or self.opt("sound", "")
        if n.sync and "sound" not in n.rule:
            return      # a volume slider moving isn't news
        if not snd:
            return
        snd = os.path.expanduser(str(snd))
        player = self.opt("sound_command", "")
        if player:
            util.spawn(f"{player} {GLib.shell_quote(snd)}")
            return
        for p in ("pw-play", "paplay", "aplay"):
            if shutil.which(p):
                util.spawn([p, snd])
                return

    # ------------------------------------------------------------- history on disk
    def _load_history(self):
        st = util.load_state(HISTORY, {})
        self.history = [h for h in st.get("history") or [] if isinstance(h, dict)]
        self.next_id = max([int(st.get("next_id") or 1)] + [int(h.get("id") or 0) + 1 for h in self.history])

    def save_soon(self):
        if not self._save_src:
            self._save_src = GLib.timeout_add_seconds(2, self._save)

    def _save(self):
        self._save_src = 0
        with self.lock:
            data = {"next_id": self.next_id, "history": list(self.history)}
        try:
            util.save_state(HISTORY, data)
        except OSError as e:
            log.warning("akashvani: couldn't save the history: %s", e)
        return False

    # ------------------------------------------------------------- for the panel
    def snapshot(self):
        """(live, history) as plain dicts, newest first; any thread."""
        with self.lock:
            live = [dict(n.public(), held=n.hidden) for n in reversed(self.live)]
            hist = [dict(h) for h in self.history]
        return live, hist

    def status(self):
        live, hist = self.snapshot()
        return {"live": len(live), "history": len(hist), "modes": sorted(self.modes), "dnd": self.dnd(),
                "held": sum(1 for n in live if n.get("held")), "owned": self.owned,
                "until": util.load_state(MODES, {}).get("until") or 0}

    def changed(self):
        for f in list(self.listeners):
            try:
                f()
            except Exception:
                log.exception("akashvani: listener failed")

    def reload(self):
        """Settings changed ([plugin.akashvani] is re-read by `vyom reload`)."""
        if self.toast:
            self.toast.restyle()
        self.changed()


MATCH_KEYS = ("app", "summary", "body", "urgency", "category", "desktop_entry", "mode", "actionable", "sync")


def image_texture(v):
    """image-data (iiibiiay) as a Gdk.Texture, or None."""
    try:
        from gi.repository import Gdk
        w, h, stride, alpha, bits, chans = (v.get_child_value(i).unpack() for i in range(6))
        data = v.get_child_value(6).get_data_as_bytes()
        if bits != 8 or chans not in (3, 4) or w <= 0 or h <= 0 or data.get_size() < stride * (h - 1) + w * chans:
            return None
        fmt = Gdk.MemoryFormat.R8G8B8A8 if alpha else Gdk.MemoryFormat.R8G8B8
        return Gdk.MemoryTexture.new(w, h, fmt, data, stride)
    except Exception as e:   # a malformed image must never cost the notification
        log.debug("akashvani: bad image-data: %s", e)
        return None
