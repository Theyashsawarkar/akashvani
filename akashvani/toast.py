"""akashvani's popups: one layer-shell window (namespace "notifications")
holding a stack of glass cards, in Vyom's look and the theme's colours.

Each card: the app's icon or the notification's image, the app and the time,
the title, the body (its markup made safe), a bar for a value (volume,
brightness, a download), and its actions as buttons. Hover holds it on
screen; a click runs its default action (or dismisses it); right click
dismisses; middle click dismisses all. More than max_visible waits behind a
"+N more" pill.

Every part has a CSS class (README "Styling"), so ~/.config/vyom/style.css
can restyle any of it; rules can add a tint (color = "green") or a class.
"""
import datetime
import html.parser
import logging
import os
import re

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

try:
    from gi.repository import Gtk4LayerShell as LayerShell
except ImportError:   # Vyom loads it; without it there are no popups, only the panel
    LayerShell = None

log = logging.getLogger("vyom.akashvani")

TINTS = ("red", "peach", "yellow", "green", "teal", "sky", "blue", "mauve", "pink", "lavender")
POSITIONS = {
    "top-right": ("top", "right"), "top-left": ("top", "left"), "top-center": ("top",),
    "bottom-right": ("bottom", "right"), "bottom-left": ("bottom", "left"), "bottom-center": ("bottom",),
    "center": (),
}


class _Markup(html.parser.HTMLParser):
    """The spec's body markup (b, i, u, a, img, br) as safe Pango markup;
    anything else keeps only its text."""
    KEEP = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "a": "u", "tt": "tt", "code": "tt", "s": "s"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.open = [], []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out.append("\n")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.out.append(GLib.markup_escape_text(alt))
        elif tag in self.KEEP:
            self.out.append(f"<{self.KEEP[tag]}>")
            self.open.append(self.KEEP[tag])

    def handle_endtag(self, tag):
        t = self.KEEP.get(tag)
        if t and t in self.open:
            while self.open:          # close in order, so the result always nests
                x = self.open.pop()
                self.out.append(f"</{x}>")
                if x == t:
                    break

    def handle_data(self, data):
        self.out.append(GLib.markup_escape_text(data))

    def result(self):
        self.close()
        return "".join(self.out) + "".join(f"</{x}>" for x in reversed(self.open))


def safe_markup(text):
    if not text:
        return ""
    p = _Markup()
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


class Toasts:
    def __init__(self, server, app):
        self.server = server
        self.app = app
        self.win = None
        self.box = None
        self.cards = {}       # id -> (revealer, note)
        self.waiting = []     # notes past max_visible, oldest first
        self.more = None      # the "+N more" pill's revealer
        self.theme = None
        self.suspended = False   # the panel is open: it shows them already

    def suspend(self, on):
        """Hide the popups while akashvani's panel is open; back after."""
        self.suspended = on
        if self.win is not None:
            self.win.set_visible(not on and bool(self.cards))

    # ------------------------------------------------------------- settings
    def opt(self, k, d):
        return self.server.opt(k, d)

    @property
    def top(self):
        return not str(self.opt("position", "top-right")).startswith("bottom")

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
        # the newest is nearest the edge it's anchored to
        for rev, _n in self.cards.values():
            rev.set_transition_type(self._transition())

    def _transition(self):
        anim = str(self.opt("animation", "slide"))
        if anim == "none":
            return Gtk.RevealerTransitionType.NONE
        if anim == "fade":
            return Gtk.RevealerTransitionType.CROSSFADE
        return Gtk.RevealerTransitionType.SLIDE_DOWN if self.top else Gtk.RevealerTransitionType.SLIDE_UP

    # ------------------------------------------------------------- show / remove
    def show(self, n, replace=None):
        w = self.window()
        if w is None:
            return
        old = self.cards.get(n["id"])
        if old is not None:                      # replaced in place (volume, brightness, replaces_id)
            rev, _ = old
            rev.set_child(self.card(n))
            self.cards[n["id"]] = (rev, n)
            return
        if n in self.waiting or any(x["id"] == n["id"] for x in self.waiting):
            self.waiting = [n if x["id"] == n["id"] else x for x in self.waiting]
            self._update_more()
            return
        if len(self.cards) >= max(1, int(self.opt("max_visible", 3))):
            if n["urgency"] == "critical":       # urgent never waits: the oldest normal one does
                bump = next((x for _, x in sorted(self.cards.values(), key=lambda c: c[1]["t"])
                             if x["urgency"] != "critical"), None)
                if bump is not None:
                    self.remove(bump, keep_waiting=True)
            else:
                self.waiting.append(n)
                self._update_more()
                return
        self._add(n)

    def _add(self, n):
        rev = Gtk.Revealer(transition_type=self._transition(),
                           transition_duration=int(self.opt("animation_ms", 220)))
        rev.set_child(self.card(n))
        self.cards[n["id"]] = (rev, n)
        if self.top:
            self.box.prepend(rev)
        else:
            self.box.append(rev)
        self._place_more()
        self.win.set_visible(not self.suspended)
        if self.more is not None:
            self._update_more()
        GLib.idle_add(lambda: (rev.set_reveal_child(True), False)[1])

    def remove(self, n, keep_waiting=False):
        if keep_waiting:
            self.waiting.insert(0, n)
        else:
            self.waiting = [x for x in self.waiting if x["id"] != n["id"]]
        got = self.cards.pop(n["id"], None)
        if got is None:
            self._update_more()
            return
        rev, _ = got

        def gone(r, _p):
            if not r.get_child_revealed() and r.get_parent() is self.box:
                self.box.remove(r)
                self._maybe_hide()
        rev.connect("notify::child-revealed", gone)
        rev.set_reveal_child(False)
        if rev.get_transition_type() == Gtk.RevealerTransitionType.NONE or not rev.get_mapped():
            gone(rev, None)
        if not keep_waiting:
            self._promote()

    def _promote(self):
        """A place freed up: the next waiting one shows."""
        while self.waiting and len(self.cards) < max(1, int(self.opt("max_visible", 3))):
            self._add(self.waiting.pop(0))
        self._update_more()

    def clear(self):
        for n in [x for _, x in self.cards.values()]:
            self.remove(n)
        self.waiting = []
        self._update_more()

    def _maybe_hide(self):
        if not self.cards and not self.waiting and self.win is not None:
            # the last card's gone: an empty window would still catch clicks
            if self.box.get_first_child() is None or (self.more and self.box.get_first_child() is self.more
                                                       and self.more.get_next_sibling() is None):
                self.win.set_visible(False)

    # ------------------------------------------------------------- "+N more"
    def _update_more(self):
        if self.box is None:
            return
        n = len(self.waiting)
        if self.more is None:
            self.more = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE, transition_duration=160)
            pill = Gtk.Button()
            pill.add_css_class("akv-more")
            pill.set_halign(Gtk.Align.CENTER)
            pill.connect("clicked", lambda *_: self.server.dismiss(every=True))
            pill.set_tooltip_text("Click to dismiss them all")
            self.more.set_child(pill)
            self._place_more()
        pill = self.more.get_child()
        pill.set_label(f"+{n} more")
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

    # ------------------------------------------------------------- one card
    def card(self, n):
        size = int(self.opt("icon_size", 44))
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("akv-card")
        card.add_css_class(f"u-{n['urgency']}")
        card.add_css_class(f"app-{slug(n['app_name'])}")
        if n.sync:
            card.add_css_class("akv-osd")
        tint = n.rule.get("color")
        if tint in TINTS:
            card.add_css_class(f"tint-{tint}")
        for c in str(n.rule.get("class") or "").split():
            card.add_css_class(c)
        card.set_size_request(int(self.opt("width", 380)), -1)

        top = Gtk.Box(spacing=12)
        icon = self.icon(n, size)
        if icon is not None:
            top.append(icon)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True, valign=Gtk.Align.CENTER)
        head = Gtk.Box(spacing=6)
        app = n["app_name"] or ""
        summary = n["summary"] or app or "Notification"
        if app and self.opt("show_app", True) and app.lower() != summary.lower():
            head.append(_label(app, "akv-app", ellipsize=Pango.EllipsizeMode.END, max_width_chars=28))
        if n["urgency"] == "critical":
            head.append(_label("Urgent", "akv-urgent"))
        if self.opt("show_time", True) and not n.sync:
            head.append(_label(datetime.datetime.fromtimestamp(n["t"]).strftime("%H:%M"), "akv-time"))
        head.append(Gtk.Box(hexpand=True))
        close = Gtk.Button(label="\U000f0156", valign=Gtk.Align.START)
        close.add_css_class("akv-close")
        close.set_tooltip_text("Dismiss")
        close.connect("clicked", lambda *_: self.server.dismiss(n["id"]))
        head.append(close)
        col.append(head)

        col.append(_label(summary, "akv-summary", lines=2))
        body = safe_markup(n.get("body") or "")
        if "value" in n and re.fullmatch(r"\s*%d\s*%%?\s*" % n["value"], body):
            body = ""    # "64%" next to a bar that says 64%
        if body.strip():
            col.append(_label(body.strip(), "akv-body", markup=True, lines=int(self.opt("body_lines", 4))))
        if "value" in n:
            bar = Gtk.ProgressBar(fraction=n["value"] / 100, hexpand=True, valign=Gtk.Align.CENTER)
            bar.add_css_class("akv-progress")
            row = Gtk.Box(spacing=10, margin_top=4)
            row.append(bar)
            row.append(_label(f"{n['value']}%", "akv-value"))
            col.append(row)
        top.append(col)
        card.append(top)

        acts = [(k, v) for k, v in n["actions"].items() if k != "default"]
        if acts and self.opt("show_actions", True):
            row = Gtk.Box(spacing=8, homogeneous=len(acts) <= 3)
            row.add_css_class("akv-actions")
            for i, (k, v) in enumerate(acts[:int(self.opt("max_actions", 3))]):
                b = Gtk.Button(label=v or k, hexpand=True)
                b.add_css_class("akv-action")
                if i == 0:
                    b.add_css_class("first")
                b.connect("clicked", lambda _b, k=k: self.server.invoke(n["id"], k))
                row.append(b)
            card.append(row)

        click = Gtk.GestureClick(button=0)
        click.connect("released", self._clicked, n)
        card.add_controller(click)
        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: self.server.pause(n))
        hover.connect("leave", lambda *_: self.server.resume(n))
        card.add_controller(hover)
        return card

    def _clicked(self, gesture, _n_press, _x, _y, n):
        b = gesture.get_current_button()
        if b == 1:
            if "default" in n["actions"]:
                self.server.invoke(n["id"], "default")
            else:
                self.server.dismiss(n["id"])
        elif b == 2:
            self.server.dismiss(every=True)
        elif b == 3:
            self.server.dismiss(n["id"])

    def icon(self, n, size):
        """The notification's image, else its icon, else the app's, else a
        bell; in a rounded tile."""
        pic = None
        if n.texture is not None:
            pic = Gtk.Image.new_from_paintable(n.texture)
            pic.set_pixel_size(size)
        else:
            for src in (n.get("image_path"), n.get("app_icon"), n.get("desktop_entry"), (n["app_name"] or "").lower()):
                pic = self._from(src, size)
                if pic is not None:
                    break
        frame = Gtk.Box(valign=Gtk.Align.START, halign=Gtk.Align.CENTER, hexpand=False)
        frame.add_css_class("akv-icon")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_size_request(size, size)
        if pic is None:
            if not self.opt("show_fallback_icon", True):
                return None
            g = _label("\U000f009a", "akv-glyph", hexpand=True, xalign=0.5)
            frame.add_css_class("glyph-tile")
            g.set_valign(Gtk.Align.CENTER)
            frame.append(g)
            return frame
        pic.set_halign(Gtk.Align.CENTER)
        pic.set_valign(Gtk.Align.CENTER)
        pic.set_hexpand(True)    # fills the tile (the tile itself stays its size)
        frame.append(pic)
        return frame

    def _from(self, src, size):
        if not src:
            return None
        src = src.removeprefix("file://")
        if src.startswith("/"):
            if not os.path.exists(src):
                return None
            if src.endswith(".svg"):    # icons drawn crisp at the tile's size
                img = Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(src)))
                img.set_pixel_size(size)
                img.add_css_class("akv-themed")
                return img
            img = Gtk.Image.new_from_paintable(cover(src, size * max(1, self.win.get_scale_factor())))
            img.set_pixel_size(size)
            return img if img.get_paintable() is not None else None
        if self.theme is not None and self.theme.has_icon(src):
            img = Gtk.Image.new_from_icon_name(src)
            img.set_pixel_size(int(size * 0.78))
            img.add_css_class("akv-themed")
            return img
        return None
