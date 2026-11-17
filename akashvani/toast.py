"""akashvani's popups: layer-shell windows (namespace "notifications") with
a stack of cards, in the theme's colours.

The card puts the content first: a quiet line with the app's small icon, its
name and how long ago; then the title and the body (paths, branches and code
set in mono); a picture only when the notification brings one; its actions
as buttons with their keys; and a hairline at the bottom that is its time
left (it stops while the pointer is on the card).

Kinds get their own card (server.classify): a phone call from ekatva (the
caller, Answer and Decline), a missed call, a text message, the phone's
other apps ("WhatsApp, on Pixel 8"), and sliders (volume, brightness) as one
slim line in their own place (osd_position).

Several from one app share one card: the newest in full, older ones as a
line each. The newest card has the focus: `akashvani key enter|1|2|3|
dismiss|next|dismiss-all` acts on it (Vayu binds them to Super+Ctrl+...).

Every part has a CSS class (README "Styling"), so ~/.config/vyom/style.css
can restyle any of it; rules can add a tint (color = "green") or a class.
"""
import datetime
import hashlib
import html.parser
import logging
import os
import re
import time

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

try:
    from gi.repository import Gtk4LayerShell as LayerShell
except ImportError:   # Vyom loads it; without it there are no popups, only the panel
    LayerShell = None

log = logging.getLogger("vyom.akashvani")

TINTS = ("red", "peach", "yellow", "green", "teal", "sky", "blue", "mauve", "pink", "lavender")
AVATAR_TINTS = ("pink", "teal", "lavender", "peach", "sky", "green", "yellow", "mauve")
POSITIONS = {
    "top-right": ("top", "right"), "top-left": ("top", "left"), "top-center": ("top",),
    "bottom-right": ("bottom", "right"), "bottom-left": ("bottom", "left"), "bottom-center": ("bottom",),
    "center": (),
}
_mono_cache = {"font": None, "at": 0.0}


def mono_font():
    """The theme's monospace font (varna's palette.json, ui.mono), checked
    at most every 5 s; "monospace" without varna."""
    now = time.monotonic()
    if _mono_cache["font"] is None or now - _mono_cache["at"] > 5:
        font = "monospace"
        state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        try:
            import json
            with open(os.path.join(state, "varna", "palette.json")) as f:
                font = (json.load(f).get("ui") or {}).get("mono") or font
        except (OSError, ValueError):
            pass
        _mono_cache.update(font=font, at=now)
    return _mono_cache["font"]
# kinds that share a card per app (calls, urgent ones and sliders never do)
GROUPABLE = ("normal", "phone", "sms", "share")
# Our own first (call, video-call: the handset and the camera as phones draw
# them, Adwaita's are mirrored), then Adwaita's.
SYMBOLIC_DIRS = (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons", "symbolic"),
                 "/usr/share/icons/Adwaita/symbolic", "/usr/share/icons/hicolor/symbolic")

# what reads as code in a body: `backticks`, paths, file:line, branches
_CODEISH = re.compile(
    r"`([^`\n]{1,80})`"
    r"|(?<![\w/@.])((?:~|\.{1,2})?/?[\w.@+-]+(?:/[\w.@+-]+)+/?)(?![\w/])"
    r"|(?<![\w/.])([\w-]+\.(?:py|go|rs|ts|tsx|js|jsx|json|toml|ya?ml|md|zip|tar|gz|xz|sh|c|h|cpp|hpp|java|kt|"
    r"lua|txt|log|png|jpe?g|pdf|svg|iso|deb|rpm|apk|lock|sql|css|html)(?::\d+)?)(?![\w])")


def _mono(text):
    return f'<span font_family="{GLib.markup_escape_text(mono_font())}">{text}</span>'


class _Markup(html.parser.HTMLParser):
    """The spec's body markup (b, i, u, a, img, br) as safe Pango markup;
    anything else keeps only its text. Code-like words outside tags are set
    in mono."""
    KEEP = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "a": "u", "tt": "tt", "code": "tt", "s": "s"}

    def __init__(self, code=""):
        super().__init__(convert_charrefs=True)
        self.out, self.open = [], []
        self.code = code

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out.append("\n")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.out.append(GLib.markup_escape_text(alt))
        elif tag in self.KEEP:
            t = self.KEEP[tag]
            self.out.append(f'<span font_family="{GLib.markup_escape_text(mono_font())}">' if t == "tt" else f"<{t}>")
            self.open.append(t)

    def handle_endtag(self, tag):
        t = self.KEEP.get(tag)
        if t and t in self.open:
            while self.open:          # close in order, so the result always nests
                x = self.open.pop()
                self.out.append("</span>" if x == "tt" else f"</{x}>")
                if x == t:
                    break

    def handle_data(self, data):
        if "tt" in self.open:
            self.out.append(GLib.markup_escape_text(data))
            return
        pos = 0
        for m in _CODEISH.finditer(data):
            self.out.append(GLib.markup_escape_text(data[pos:m.start()]))
            word = m.group(1) or m.group(2) or m.group(3)
            self.out.append(_mono(GLib.markup_escape_text(word)))
            pos = m.end()
        rest = GLib.markup_escape_text(data[pos:])
        if self.code:      # the one-time code stands out
            rest = re.sub(r"(?<!\d)(" + r"[ -]?".join(re.escape(c) for c in self.code) + r")(?!\d)",
                          lambda m: _mono(f"<b>{m.group(1)}</b>"), rest)
        self.out.append(rest)

    def result(self):
        self.close()
        return "".join(self.out) + "".join("</span>" if x == "tt" else f"</{x}>" for x in reversed(self.open))


def safe_markup(text, code=""):
    if not text:
        return ""
    p = _Markup(code)
    try:
        p.feed(text)
        out = p.result()
        Pango.parse_markup(out, -1, "\0")
        return out
    except Exception:
        return GLib.markup_escape_text(re.sub(r"<[^>]+>", "", text))


def _label(text, *classes, markup=False, lines=0, **props):
    props.setdefault("xalign", 0)
    w = Gtk.Label(**props)
    if markup:
        w.set_markup(text)
    else:
        w.set_text(text)
    for c in classes:
        w.add_css_class(c)
    if lines:
        w.set_wrap(True)
        w.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        w.set_lines(lines)
        w.set_ellipsize(Pango.EllipsizeMode.END)
    if (lines or props.get("ellipsize")) and "max_width_chars" not in props:
        # A wrapped or cut line asks for no width of its own (its natural width
        # would be the whole text, one line): it takes the card's. Every toast
        # is then exactly the card's width, however long its text.
        w.set_max_width_chars(1)
        w.set_hexpand(True)
    return w


def cover(path, px):
    """A picture file cropped to a square and scaled to px (a photo or a
    screenshot fills its tile, like CSS's object-fit: cover)."""
    try:
        from gi.repository import GdkPixbuf
        pb = GdkPixbuf.Pixbuf.new_from_file(path)
    except (GLib.Error, ImportError, ValueError):
        return None
    w, h = pb.get_width(), pb.get_height()
    side = min(w, h)
    pb = pb.new_subpixbuf((w - side) // 2, (h - side) // 2, side, side)
    pb = pb.scale_simple(px, px, GdkPixbuf.InterpType.BILINEAR) if side > px else pb
    return Gdk.Texture.new_for_pixbuf(pb)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "app"


def ago(t, now=None):
    """'now', '4m', '2h', or the time for older ones."""
    d = max(0, (now or time.time()) - (t or 0))
    if d < 45:
        return "now"
    if d < 3600:
        return f"{int(d // 60) or 1}m"
    if d < 6 * 3600:
        return f"{int(d // 3600)}h"
    return datetime.datetime.fromtimestamp(t).strftime("%H:%M")


def initials(name):
    words = re.findall(r"[^\W\d_]+", name or "")
    if not words:
        return "#" if re.search(r"\d", name or "") else "?"
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()


def mask_number(num):
    """+91 98••• ••142: enough to recognise, not the whole number on screen."""
    digits = re.sub(r"\D", "", num or "")
    if len(digits) < 7:
        return num or ""
    cc = "+" + digits[:-10] + " " if num.strip().startswith("+") and len(digits) > 10 else ""
    rest = digits[-10:] if cc else digits
    return f"{cc}{rest[:2]}••• ••{rest[-3:]}"


class Slot:
    """One card on screen: one notification, or several from one app."""
    __slots__ = ("kc", "key", "notes", "rev", "ring", "time_labels", "timer")

    def __init__(self, key):
        self.key = key
        self.rev = None
        self.notes = []          # newest first
        self.kc = []             # its keycaps (shown on the focused card)
        self.time_labels = []    # (label, note): "now", "4m"... kept fresh
        self.timer = None        # the time-left line
        self.ring = None         # a call's ringing-for label

    @property
    def main(self):
        return self.notes[0]

    @property
    def rank(self):
        n = self.main
        if n["kind"] == "call":
            return 0
        return 1 if n["urgency"] == "critical" else 2


class Toasts:
    """The popups, in two places: notifications at `position`, and sliders
    (volume, brightness) at `osd_position`. Without osd_position they share
    one stack. Every setting can be given again with an osd_ prefix
    (osd_width, osd_margin_x...) for the sliders alone."""

    def __init__(self, server, app):
        self.server = server
        self.main = Lane(server, app)
        self.osd = Lane(server, app, "osd_")

    def lane(self, n):
        if self.server.opt("osd_position", None) and n.get("kind") == "osd":
            return self.osd
        return self.main

    def lanes(self):
        return (self.main, self.osd)

    def show(self, n, replace=None):
        to = self.lane(n)
        for ln in self.lanes():
            if ln is not to and ln.has(n):
                ln.remove(n)    # it moved (osd_position changed, or it became a slider)
        to.show(n, replace)

    def remove(self, n, keep_waiting=False):
        for ln in self.lanes():
            ln.remove(n, keep_waiting)

    def clear(self):
        for ln in self.lanes():
            ln.clear()

    def suspend(self, on):
        for ln in self.lanes():
            ln.suspend(on)

    def restyle(self):
        for ln in self.lanes():
            ln.restyle()

    @property
    def suspended(self):
        return self.main.suspended

    def key(self, name):
        """A key from `akashvani key NAME`, on the focused card."""
        return self.main.key(name)


class Lane:
    """One layer-shell window with a stack of cards."""

    def __init__(self, server, app, prefix=""):
        self.server = server
        self.app = app
        self.prefix = prefix
        self.win = None
        self.box = None
        self.slots = []        # on screen, in order (the first is nearest the edge)
        self.cards = {}        # note id -> Slot
        self.waiting = []      # notes past max_visible, oldest first
        self.more = None       # the "N more waiting" pill's revealer
        self.theme = None
        self.focus = 0         # index into self.slots
        self.suspended = False   # the panel is open: it shows them already
        self._tick_src = 0
        self._ticks = 0

    def suspend(self, on):
        """Hide the popups while akashvani's panel is open; back after."""
        self.suspended = on
        if self.win is not None:
            self.win.set_visible(not on and bool(self.slots))

    # ------------------------------------------------------------- settings
    def opt(self, k, d):
        if self.prefix:
            v = self.server.opt(self.prefix + k, None)
            if v is not None:
                return v
        return self.server.opt(k, d)

    @property
    def top(self):
        return not str(self.opt("position", "top-right")).startswith("bottom")

    @property
    def keyed(self):
        """This lane's focused card answers the keys (the notifications, not the sliders)."""
        return not self.prefix and bool(self.opt("keys", True))

    def max_visible(self):
        return max(1, int(self.opt("max_visible", 3)))

    def has(self, n):
        return n["id"] in self.cards or any(x["id"] == n["id"] for x in self.waiting)

    # ------------------------------------------------------------- the window
    def window(self):
        if self.win is not None:
            return self.win
        if LayerShell is None or not LayerShell.is_supported():
            log.warning("akashvani: no layer-shell; notifications only show in the panel")
            return None
        w = Gtk.Window(application=self.app, resizable=False, decorated=False)
        w.add_css_class("akashvani-toasts")
        LayerShell.init_for_window(w)
        LayerShell.set_namespace(w, "notifications")
        # top: under Vyom's panels (overlay), over windows; "overlay" puts
        # them over fullscreen windows too
        layer = LayerShell.Layer.OVERLAY if self.opt("layer", "top") == "overlay" else LayerShell.Layer.TOP
        LayerShell.set_layer(w, layer)
        LayerShell.set_keyboard_mode(w, LayerShell.KeyboardMode.NONE)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.add_css_class("akv-stack")
        w.set_child(self.box)
        self.win = w
        self.restyle()
        try:
            self.theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        except TypeError:
            self.theme = None
        return w

    def restyle(self):
        """Position, margins and gap from the settings (again on reload)."""
        if self.win is None:
            return
        pos = str(self.opt("position", "top-right"))
        edges = POSITIONS.get(pos, POSITIONS["top-right"])
        mx, my = self.opt("margin_x", 16), self.opt("margin_y", 12)
        e = {"top": LayerShell.Edge.TOP, "bottom": LayerShell.Edge.BOTTOM,
             "left": LayerShell.Edge.LEFT, "right": LayerShell.Edge.RIGHT}
        for name, edge in e.items():
            on = name in edges
            LayerShell.set_anchor(self.win, edge, on)
            LayerShell.set_margin(self.win, edge, int(my if name in ("top", "bottom") else mx) if on else 0)
        self.box.set_spacing(int(self.opt("gap", 10)))
        for sl in self.slots:
            sl.rev.set_transition_type(self._transition())

    def _transition(self):
        anim = str(self.opt("animation", "slide"))
        if anim == "none":
            return Gtk.RevealerTransitionType.NONE
        if anim == "fade":
            return Gtk.RevealerTransitionType.CROSSFADE
        return Gtk.RevealerTransitionType.SLIDE_DOWN if self.top else Gtk.RevealerTransitionType.SLIDE_UP

    # ------------------------------------------------------------- show / remove
    def group_key(self, n):
        if self.prefix or n["kind"] not in GROUPABLE or n["urgency"] == "critical" or n.sync \
                or not self.opt("group", True):
            return f"id:{n['id']}"
        return "app:" + (n["app_name"] or "") + "|" + (n.get("via") or "")

    def show(self, n, replace=None):
        w = self.window()
        if w is None:
            return
        sl = self.cards.get(n["id"])
        if sl is not None:                      # replaced in place (volume, brightness, replaces_id)
            sl.notes = [n if x["id"] == n["id"] else x for x in sl.notes]
            self._build(sl)
            return
        if any(x["id"] == n["id"] for x in self.waiting):
            self.waiting = [n if x["id"] == n["id"] else x for x in self.waiting]
            self._update_more()
            return
        key = self.group_key(n)
        sl = next((s for s in self.slots if s.key == key), None)
        if sl is not None:                      # one more from this app: it joins its card
            sl.notes.insert(0, n)
            self.cards[n["id"]] = sl
            self._build(sl)
            self._reorder(new=sl)
            return
        if len(self.slots) >= self.max_visible():
            rank = 0 if n["kind"] == "call" else 1 if n["urgency"] == "critical" else 2
            # a call or an urgent one never waits: the oldest ordinary card does
            bump = next((s for s in sorted(self.slots, key=lambda s: s.main["t"]) if s.rank > rank), None)
            if bump is None:
                self.waiting.append(n)
                self._update_more()
                return
            for x in bump.notes:
                self.remove(x, keep_waiting=True)
        self._add(n, key)

    def _add(self, n, key):
        sl = Slot(key)
        sl.notes = [n]
        sl.rev = Gtk.Revealer(transition_type=self._transition(),
                              transition_duration=int(self.opt("animation_ms", 220)))
        self.cards[n["id"]] = sl
        self.slots.append(sl)
        self._build(sl)
        self.box.append(sl.rev)
        self._reorder(new=sl)
        self.win.set_visible(not self.suspended)
        self._update_more()
        self._start_tick()
        rev = sl.rev
        # only if it's still here: dismissed before this ran, it would come back as a ghost
        GLib.idle_add(lambda: (sl in self.slots and rev.set_reveal_child(True), False)[1])

    def remove(self, n, keep_waiting=False):
        if keep_waiting:
            self.waiting.insert(0, n)
        else:
            self.waiting = [x for x in self.waiting if x["id"] != n["id"]]
        sl = self.cards.pop(n["id"], None)
        if sl is None:
            self._update_more()
            return
        sl.notes = [x for x in sl.notes if x["id"] != n["id"]]
        if sl.notes:                       # the rest of its group stays
            self._build(sl)
            return
        self.slots.remove(sl)
        rev = sl.rev

        def gone(r, _p):
            if not r.get_child_revealed() and r.get_parent() is self.box:
                self.box.remove(r)
                self._maybe_hide()
        rev.connect("notify::child-revealed", gone)
        rev.set_reveal_child(False)
        if rev.get_transition_type() == Gtk.RevealerTransitionType.NONE or not rev.get_mapped():
            gone(rev, None)
        self.focus = min(self.focus, max(0, len(self.slots) - 1))
        if not keep_waiting:
            self._promote()
        self._refocus()

    def _promote(self):
        """A place freed up: the next waiting one shows."""
        while self.waiting and len(self.slots) < self.max_visible():
            n = self.waiting.pop(0)
            if n in self.server.live and not n.hidden:
                self.show(n)
        self._update_more()

    def clear(self):
        """Everything goes at once: nothing waiting is promoted on the way."""
        self.waiting = []
        for sl in list(self.slots):
            for n in list(sl.notes):
                self.remove(n)
        self._update_more()

    def _maybe_hide(self):
        if not self.slots and not self.waiting and self.win is not None:
            # the last card's gone: an empty window would still catch clicks
            if self.box.get_first_child() is None or (self.more and self.box.get_first_child() is self.more
                                                       and self.more.get_next_sibling() is None):
                self.win.set_visible(False)

    def _reorder(self, new=None):
        """Calls first, then urgent ones, then the newest: nearest the edge
        the stack hangs from. A new card takes the focus."""
        self.slots.sort(key=lambda s: (s.rank, -s.main["t"]))
        order = self.slots if self.top else list(reversed(self.slots))
        prev = None
        for sl in order:
            self.box.reorder_child_after(sl.rev, prev)
            prev = sl.rev
        self._place_more()
        if new is not None:
            self.focus = 0
        self._refocus()

    # ------------------------------------------------------------- focus and keys
    def focused(self):
        if not self.slots:
            return None
        return self.slots[min(self.focus, len(self.slots) - 1)]

    def _refocus(self):
        f = self.focused() if self.keyed else None
        for sl in self.slots:
            card = sl.rev.get_child()
            if card is None:
                continue
            on = sl is f
            if on:
                card.add_css_class("focus")
            else:
                card.remove_css_class("focus")
            for k in sl.kc:
                k.set_visible(on)

    def key(self, name):
        sl = self.focused()
        if sl is None:
            return False
        n = sl.main
        if name == "next":
            self.focus = (self.focus + 1) % len(self.slots)
            self._refocus()
            return True
        if name == "dismiss-all":
            return self.server.dismiss(every=True)
        btns = self.buttons(n)
        if name == "dismiss":
            if n["kind"] == "call" and "reject" in n["actions"]:
                return self.server.invoke(n["id"], "reject")
            return self.dismiss_slot(sl)
        if name == "enter":
            if n["kind"] == "call" and "answer" in n["actions"]:
                return self.server.invoke(n["id"], "answer")
            if "default" in n["actions"]:
                return self.server.invoke(n["id"], "default")
            if btns:
                return self.server.invoke(n["id"], btns[0][0])
            return self.dismiss_slot(sl)
        if name.isdigit():
            i = int(name) - 1
            if 0 <= i < len(btns):
                return self.server.invoke(n["id"], btns[i][0])
        return False

    def dismiss_slot(self, sl):
        ok = False
        for n in list(sl.notes):
            ok = self.server.dismiss(n["id"]) or ok
        return ok

    def buttons(self, n):
        """[(action key, label)] as the card shows them, in key order."""
        acts = [(k, v or k) for k, v in n["actions"].items() if k != "default"]
        if n["kind"] == "call":
            first = [a for a in acts if a[0] == "reject"]
            last = [a for a in acts if a[0] == "answer"]
            mid = [a for a in acts if a[0] not in ("reject", "answer")]
            # Answer first (left), Reject last (right), as on a phone's call screen.
            return (last + mid[:1] + first) if self.opt("show_actions", True) else []
        if not self.opt("show_actions", True):
            return []
        if n["kind"] == "missed":
            # It waits for you, so it says how to be done with it: call back
            # (when the phone app offers it) or dismiss.
            return [a for a in acts if a[0] != "akv:dismiss"][:1] + [a for a in acts if a[0] == "akv:dismiss"]
        return acts[:int(self.opt("max_actions", 3))]

    # ------------------------------------------------------------- the clock
    def _start_tick(self):
        if not self._tick_src:
            self._tick_src = GLib.timeout_add(100, self._tick)

    def _tick(self):
        if not self.slots:
            self._tick_src = 0
            return False
        self._ticks += 1
        now = time.time()
        for sl in self.slots:
            if sl.timer is not None:
                f = self.server.remaining(sl.main)
                if f is not None:
                    sl.timer.set_fraction(f)
            if self._ticks % 10 == 0:
                for lab, n in sl.time_labels:
                    lab.set_text(ago(n["t"], now))
                if sl.ring is not None:
                    d = int(now - sl.main["t"])
                    sl.ring.set_text(f"{d // 60}:{d % 60:02d}")
        return True

    # ------------------------------------------------------------- "N more waiting"
    def _update_more(self):
        if self.box is None:
            return
        n = len(self.waiting)
        if self.more is None:
            self.more = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE, transition_duration=160)
            pill = Gtk.Button()
            pill.add_css_class("akv-more")
            pill.set_halign(Gtk.Align.CENTER)
            pill.set_child(_label("", "akv-more-label", markup=True))
            pill.connect("clicked", lambda *_: self.server.plugin_open())
            pill.set_tooltip_text("Open them in the panel")
            self.more.set_child(pill)
            self._place_more()
        self.more.get_child().get_child().set_markup(f'<span font_family="{GLib.markup_escape_text(mono_font())}" weight="bold">{n}</span> more waiting')
        self.more.set_reveal_child(n > 0)
        self.more.set_visible(n > 0)
        if n == 0:
            self._maybe_hide()

    def _place_more(self):
        if self.more is None:
            return
        if self.more.get_parent() is self.box:
            self.box.remove(self.more)
        if self.top:
            self.box.append(self.more)
        else:
            self.box.prepend(self.more)

    # ------------------------------------------------------------- cards
    def _build(self, sl):
        sl.kc, sl.time_labels, sl.timer, sl.ring = [], [], None, None
        n = sl.main
        if n["kind"] == "osd":
            card = self._osd(sl)
        elif n["kind"] == "call":
            card = self._call(sl)
        else:
            card = self._card(sl)
        card.set_size_request(int(self.opt("width", 400)), -1)
        for c in str(n.rule.get("class") or "").split():
            card.add_css_class(c)
        tint = n.rule.get("color")
        if tint in TINTS:
            card.add_css_class(f"tint-{tint}")
        click = Gtk.GestureClick(button=0)
        click.connect("released", self._clicked, sl)
        card.add_controller(click)
        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: [self.server.pause(x) for x in sl.notes])
        hover.connect("leave", lambda *_: [self.server.resume(x) for x in sl.notes])
        card.add_controller(hover)
        sl.rev.set_child(card)
        self._refocus()

    def _shell(self, n, *classes):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        urgency = "call" if n["kind"] == "call" else n["urgency"]   # a call is urgent, but green, not red
        for c in ("akv-card", f"u-{urgency}", f"k-{n['kind']}", f"app-{slug(n['app_name'])}", *classes):
            card.add_css_class(c)
        return card

    def _meta(self, sl, n, count=0):
        """The quiet line: icon, app, where from, a tag, the count, the time, close."""
        row = Gtk.Box(spacing=7)
        row.add_css_class("akv-meta")
        icon = self.app_icon(n)
        if icon is not None:
            row.append(icon)
        row.append(_label(n["app_name"] or "Notification", "akv-app",
                          ellipsize=Pango.EllipsizeMode.END, max_width_chars=26))
        if n.get("via") and n["kind"] != "call":
            row.append(_label(f"on {n['via']}", "akv-via", ellipsize=Pango.EllipsizeMode.END, max_width_chars=18))
        tag = self.tag(n)
        if tag:
            row.append(_label(tag[0], "akv-tag", tag[1]))
        if count > 1:
            row.append(_label(str(count), "akv-count"))
        row.append(Gtk.Box(hexpand=True))
        # A ringing call has no clock: the "ringing" tag says it all (it counted
        # how long it had rung, which read as a call's length).
        if n["kind"] != "call" and self.opt("show_time", True):
            t = _label(ago(n["t"]), "akv-time")
            sl.time_labels.append((t, n))
            row.append(t)
        close = Gtk.Button(valign=Gtk.Align.CENTER)
        close.set_child(self.symbolic("window-close-symbolic", 12))
        close.add_css_class("akv-close")
        close.set_tooltip_text("Dismiss")
        close.connect("clicked", lambda *_: self.dismiss_slot(sl))
        row.append(close)
        return row

    def tag(self, n):
        if n["kind"] == "call":
            return ("video call" if n.get("video") else "ringing", "green")
        if n["kind"] == "missed":
            return ("missed", "red")
        if n["urgency"] == "critical":
            return (n.rule.get("tag") or "urgent", "red")
        if n.hidden:
            return ("held", "yellow")
        return None

    def _card(self, sl):
        n = sl.main
        card = self._shell(n)
        card.append(self._meta(sl, n, len(sl.notes)))

        row = Gtk.Box(spacing=12)
        row.add_css_class("akv-content")
        person = n["kind"] in ("sms", "phone", "missed") or (n.get("category") or "").startswith("im")
        pic = self.picture(n, 38, round_=person or n.texture is not None)
        if pic is None and person and n.get("contact"):
            pic = self.initials(n["contact"], 38)
        if pic is not None:
            pic.set_valign(Gtk.Align.START)
            row.append(pic)
        # A clear gap between the title and its message: they never touch.
        # Every card the same size: one line of title, at most two of message,
        # each cut with "…", in a block of fixed height (a short one is as tall
        # as a long one).
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True, valign=Gtk.Align.START)
        col.add_css_class("akv-text")
        title = n.title or n["summary"] or n["app_name"] or "Notification"
        col.append(_label(title, "akv-summary", lines=1))
        body = safe_markup(n.get("body") or "", n.code)
        if n["kind"] == "missed" and not body.strip():
            # A missed call's second line: the number (masked, as on the ringing
            # card) and what it was, like WhatsApp's own "5 missed calls".
            num = mask_number(n.get("number") or "")
            body = GLib.markup_escape_text(f"{num} · missed call" if num else "Missed call")
        if "value" in n and re.fullmatch(r"\s*%d\s*%%?\s*" % n["value"], body):
            body = ""
        if body.strip():
            col.append(_label(body.strip(), "akv-body", markup=True, lines=int(self.opt("body_lines", 2))))
        if "value" in n:
            bar = Gtk.ProgressBar(fraction=n["value"] / 100, hexpand=True, valign=Gtk.Align.CENTER)
            bar.add_css_class("akv-progress")
            vr = Gtk.Box(spacing=10, margin_top=6)
            vr.append(bar)
            vr.append(_label(f"{n['value']}%", "akv-value", width_chars=4, xalign=1))
            col.append(vr)
        row.append(col)
        card.append(row)

        if len(sl.notes) > 1:              # older ones from this app: one line, always
            older = Gtk.Box(spacing=10)
            older.add_css_class("akv-older")
            x = sl.notes[1]
            body = re.sub(r"<[^>]+>", "", x.get("body") or "").strip()
            text = " · ".join(t for t in (x.title or x["summary"] or "", body) if t)
            extra = len(sl.notes) - 2
            if extra > 0:
                text += f", and {extra} more"
            older.append(_label(text, "akv-older-text", hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            t = _label(ago(x["t"]), "akv-older-time")
            sl.time_labels.append((t, x))
            older.append(t)
            card.append(older)

        btns = self.buttons(n)
        if btns:
            card.append(self._actions(sl, n, btns))
        self._timer(sl, card)
        return card

    def _actions(self, sl, n, btns):
        row = Gtk.Box(spacing=6, homogeneous=True)
        row.add_css_class("akv-actions")
        for i, (k, v) in enumerate(btns):
            b = Gtk.Button(hexpand=True)
            b.add_css_class("akv-action")
            inner = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
            cap = str(i + 1)
            if n["kind"] == "call" and k == "answer":
                b.add_css_class("answer")
                # A video call answers with a camera: easy to tell at a glance.
                inner.append(self.symbolic("video-call-symbolic" if n.get("video") else "call-symbolic", 15))
                cap = "⏎"
            elif n["kind"] == "call" and k == "reject":
                b.add_css_class("decline")
                inner.append(self.symbolic("call-stop-symbolic", 15))
                cap = "⌫"
            elif i == 0:
                b.add_css_class("first")
            if k == "akv:copy":
                inner.append(self.symbolic("edit-copy-symbolic", 14))
            inner.append(_label(v, "akv-action-label", ellipsize=Pango.EllipsizeMode.END, xalign=0.5,
                                max_width_chars=16))
            kc = _label(cap, "akv-kc", valign=Gtk.Align.CENTER)
            sl.kc.append(kc)
            inner.append(kc)
            b.set_child(inner)
            if k == "akv:dismiss":
                b.connect("clicked", lambda *_: self.dismiss_slot(sl))
            else:
                b.connect("clicked", lambda _b, k=k: self.server.invoke(n["id"], k))
            row.append(b)
        return row

    def _timer(self, _sl, card):
        """No time-left line at the bottom (it read as clutter): every card ends
        the same, with the same padding, timed or not."""
        card.add_css_class("untimed")

    def _call(self, sl):
        n = sl.main
        card = self._shell(n, "akv-call")
        card.append(self._meta(sl, n))
        who = Gtk.Box(spacing=14)
        who.add_css_class("akv-who")
        ring = Gtk.Box()
        ring.add_css_class("akv-ring")
        pic = self.picture(n, 52, round_=True) or self.initials(n.get("contact") or n.title, 52)
        ring.append(pic)
        who.append(ring)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, hexpand=True)
        col.append(_label(n.get("contact") or n.title or "Unknown caller", "akv-caller",
                          ellipsize=Pango.EllipsizeMode.END))
        sub = mask_number(n.get("number") or "") if n.get("number") else (n.get("body") or "").strip()
        if sub:
            col.append(_label(sub, "akv-number", ellipsize=Pango.EllipsizeMode.END))
        who.append(col)
        card.append(who)
        btns = self.buttons(n)
        if btns:
            card.append(self._actions(sl, n, btns))
        card.add_css_class("untimed")
        return card

    def _osd(self, sl):
        n = sl.main
        card = Gtk.Box(spacing=12)
        for c in ("akv-osd", f"app-{slug(n['app_name'])}"):
            card.add_css_class(c)
        muted = n.get("value", 0) == 0 and re.search(r"mute|off", f"{n.get('body') or ''} {n.get('app_icon') or ''}", re.IGNORECASE)
        if muted:
            card.add_css_class("muted")
        icon = None
        name = n.get("app_icon") or ""
        if name and not name.startswith("/"):
            icon = self.symbolic(name if name.endswith("-symbolic") else name + "-symbolic", 18, quiet=True)
        if icon is None:
            icon = self.app_icon(n, 18)
        if icon is not None:
            card.append(icon)
        bar = Gtk.ProgressBar(fraction=n.get("value", 0) / 100, hexpand=True, valign=Gtk.Align.CENTER)
        bar.add_css_class("akv-osd-bar")
        card.append(bar)
        card.append(_label("off" if muted else str(n.get("value", 0)), "akv-osd-value", width_chars=3, xalign=1))
        card.set_tooltip_text(n["summary"] or n["app_name"])
        return card

    def _clicked(self, gesture, _n_press, _x, _y, sl):
        n = sl.main
        b = gesture.get_current_button()
        if b == 1:
            if n["kind"] == "call":
                return     # a stray click never answers or ends a call: its buttons do
            if "default" in n["actions"]:
                self.server.invoke(n["id"], "default")
            else:
                self.dismiss_slot(sl)
        elif b == 2:
            self.server.dismiss(every=True)
        elif b == 3:
            self.dismiss_slot(sl)

    # ------------------------------------------------------------- pictures and icons
    def symbolic(self, name, size, quiet=False):
        """A symbolic icon in the text's colour, from the theme or Adwaita's files."""
        img = None
        if self.theme is not None and self.theme.has_icon(name):
            img = Gtk.Image.new_from_icon_name(name)
        else:
            for d in SYMBOLIC_DIRS:
                for sub in ("actions", "status", "devices", "ui", "apps", "places", "mimetypes"):
                    f = os.path.join(d, sub, name + ".svg")
                    if os.path.exists(f):
                        img = Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(f)))
                        break
                if img is not None:
                    break
        if img is None:
            return None if quiet else _label("•", "akv-glyph")
        img.set_pixel_size(size)
        img.add_css_class("akv-sym")
        img.set_hexpand(False)
        img.set_valign(Gtk.Align.CENTER)
        return img

    def app_icon(self, n, size=16):
        """The small icon on the meta line."""
        kind_icon = {"call": "call-symbolic", "missed": "call-missed-symbolic", "sms": "mail-unread-symbolic",
                     "share": "phone-symbolic"}.get(n["kind"])
        if n["kind"] == "call" and n.get("video"):
            kind_icon = "video-call-symbolic"
        if kind_icon:
            img = self.symbolic(kind_icon, size - 4 if size > 14 else size, quiet=True)
            if img is not None:
                frame = Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.CENTER, hexpand=False)
                frame.add_css_class("akv-appicon-tile")
                frame.add_css_class(f"k-{n['kind']}")
                frame.set_size_request(size, size)
                img.set_halign(Gtk.Align.CENTER)
                img.set_valign(Gtk.Align.CENTER)
                img.set_hexpand(False)
                frame.append(img)
                frame.set_hexpand(False)
                return frame
        for src in (n.get("app_icon") if not n.texture else None, n.get("desktop_entry"),
                    (n["app_name"] or "").lower(), slug(n["app_name"])):
            img = self._from(src, size)
            if img is not None:
                img.add_css_class("akv-appicon")
                img.set_hexpand(False)
                img.set_valign(Gtk.Align.CENTER)
                return img
        # no icon anywhere: its first letter in a small tile
        frame = Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        frame.add_css_class("akv-appicon-tile")
        frame.add_css_class(f"av-{AVATAR_TINTS[self._hash(n['app_name']) % len(AVATAR_TINTS)]}")
        frame.set_size_request(size, size)
        frame.append(_label((n["app_name"] or "?")[:1].upper(), "akv-appicon-letter", xalign=0.5, width_chars=1,
                            halign=Gtk.Align.CENTER, hexpand=True))
        frame.set_hexpand(False)
        return frame

    def picture(self, n, size, round_=False):
        """The notification's own picture (image-data, image-path), or None."""
        scale = max(1, self.win.get_scale_factor()) if self.win else 1
        tex = n.texture
        if tex is None and n.get("image_path") and os.path.exists(n["image_path"]):
            tex = cover(n["image_path"], size * scale)
        if tex is None:
            return None
        img = Gtk.Image.new_from_paintable(tex)
        img.set_pixel_size(size)
        frame = Gtk.Box(valign=Gtk.Align.START, halign=Gtk.Align.CENTER, hexpand=False)
        frame.add_css_class("akv-avatar" if round_ else "akv-pic")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_size_request(size, size)
        img.set_hexpand(True)
        frame.append(img)
        return frame

    def initials(self, name, size):
        frame = Gtk.Box(valign=Gtk.Align.START, halign=Gtk.Align.CENTER, hexpand=False)
        frame.add_css_class("akv-avatar")
        frame.add_css_class("akv-initials")
        frame.add_css_class(f"av-{AVATAR_TINTS[self._hash(name) % len(AVATAR_TINTS)]}")
        if size > 44:
            frame.add_css_class("big")
        frame.set_size_request(size, size)
        lab = _label(initials(name), "akv-initials-text", hexpand=True, xalign=0.5)
        lab.set_valign(Gtk.Align.CENTER)
        frame.append(lab)
        return frame

    @staticmethod
    def _hash(s):
        return int(hashlib.md5((s or "").encode()).hexdigest()[:6], 16)

    def _from(self, src, size):
        if not src:
            return None
        src = str(src).removeprefix("file://")
        if src.startswith("/"):
            if not os.path.exists(src):
                return None
            if src.endswith(".svg"):
                img = Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(src)))
                img.set_pixel_size(size)
                return img
            scale = max(1, self.win.get_scale_factor()) if self.win else 1
            img = Gtk.Image.new_from_paintable(cover(src, size * scale))
            img.set_pixel_size(size)
            return img if img.get_paintable() is not None else None
        if self.theme is not None and self.theme.has_icon(src):
            img = Gtk.Image.new_from_icon_name(src)
            img.set_pixel_size(size)
            return img
        return None
