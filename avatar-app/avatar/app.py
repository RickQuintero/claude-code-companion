"""The avatar window: a small transparent, always-on-top, click-through overlay.  Run:  python -m avatar.app"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QGuiApplication, QIcon, QImage, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from .animator import Animator
from .config import CONFIG_PATH, ROOT, load_config, save_config
from .pack import discover_packs, load_pack_or_default
from .placement import CORNERS, anchor_from_position, clamp, place
from .statefile import read_speaking, read_state
from .states import effective_state

LOCK_PATH = ROOT / "state" / "app.lock"
PACKS_DIR = ROOT / "packs"
DEFAULT_PACK = PACKS_DIR / "default"
HOVER_FADE_S = 0.15          # how long the see-through circle takes to fade in or out
FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
         | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)


class AvatarWindow(QWidget):
    def __init__(self, cfg: dict, state_path: Path, default_pack: Path = DEFAULT_PACK, clock=time.time,
                 rng: random.Random | None = None, config_path: Path | None = None, place_fn=place,
                 packs_dir: Path = PACKS_DIR, cursor_fn=QCursor.pos):
        super().__init__(None, FLAGS)
        self.cfg, self.state_path, self.clock = dict(cfg), Path(state_path), clock
        self.config_path, self._place, self.packs_dir, self._rng = config_path, place_fn, Path(packs_dir), rng
        self._cursor_fn = cursor_fn
        self.hover_amount = 0.0                   # 0 = solid, 1 = the see-through circle is fully cut
        self._hover_center, self._hover_t = QPoint(0, 0), None
        self._moving = False
        self._move_action = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        chosen = Path(self.cfg["pack"])
        chosen = chosen if chosen.is_absolute() else ROOT / chosen
        self.pack, self.pack_error = load_pack_or_default(chosen, Path(default_pack))
        self.animator = Animator(rng or random.Random(), self.pack.blink_min, self.pack.blink_max, self.pack.blink_ms)
        self._last_record: dict | None = None
        self._cache: dict = {}
        self._path = self.pack.image("idle", 0, False, False)
        self._lock: QLockFile | None = None
        self._drag_offset: QPoint | None = None
        self.tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None

        self._apply_size()
        self.reposition()
        app = QGuiApplication.instance()
        if app is not None:
            app.primaryScreenChanged.connect(self.on_screen_changed)
            app.screenAdded.connect(self.on_screen_changed)
            app.screenRemoved.connect(self.on_screen_changed)
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                screen.availableGeometryChanged.connect(self.on_screen_changed)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh)
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(33)          # about 30 Hz: smooth enough to follow the mouse
        self.hover_timer.timeout.connect(self.update_hover)

    # ---------------------------------------------------------------- what to show
    def current_image_path(self) -> Path:
        return self._path

    def refresh(self) -> None:
        """One 10 Hz tick: read the files, choose the picture."""
        now = self.clock()
        record = read_state(self.state_path)
        if record is not None:                     # a missing or half-written file keeps the last good state
            self._last_record = record
        state = effective_state(self._last_record, now)
        speaking = read_speaking(Path(self.cfg["speaking_file"]), now)
        mouth, blink = self.animator.tick(now, speaking)
        path = self.pack.image(state, int(now * self.pack.fps), mouth, blink)
        if path != self._path:
            self._path = path
            self.update()

    def paintEvent(self, _event) -> None:
        pm = self._scaled(self._path)
        if pm is None:
            return
        p = QPainter(self)
        p.setOpacity(float(self.cfg["opacity"]))
        radius = int(self.cfg.get("hover_radius", 0))
        if self.hover_amount <= 0 or radius <= 0:
            p.drawPixmap(0, 0, pm)
            return
        img = QImage(pm.size(), QImage.Format.Format_ARGB32_Premultiplied)         # the picture with a soft hole cut in it
        img.fill(0)
        img.setDevicePixelRatio(pm.devicePixelRatio())
        q = QPainter(img)
        q.drawPixmap(0, 0, pm)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        centre, alpha = QPointF(self._hover_center), round(255 * self.hover_amount)
        grad = QRadialGradient(centre, radius)
        grad.setColorAt(0.0, QColor(0, 0, 0, alpha))
        grad.setColorAt(0.55, QColor(0, 0, 0, alpha))                               # fully clear in the middle,
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))                                    # fading out towards the edge
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QBrush(grad))
        q.drawEllipse(centre, float(radius), float(radius))
        q.end()
        p.drawImage(0, 0, img)

    def update_hover(self) -> None:
        """The window is click-through and gets no mouse events, so ask where the cursor is and fade the circle."""
        now = self.clock()
        dt = 0.0 if self._hover_t is None else max(0.0, now - self._hover_t)
        self._hover_t = now
        radius = int(self.cfg.get("hover_radius", 0))
        local = self.mapFromGlobal(self._cursor_fn())
        inside = radius > 0 and not self._moving and self.rect().contains(local)
        target, step = (1.0 if inside else 0.0), dt / HOVER_FADE_S
        amount = min(target, self.hover_amount + step) if target > self.hover_amount else max(target, self.hover_amount - step)
        changed = amount != self.hover_amount or (inside and local != self._hover_center)
        if inside:
            self._hover_center = local
        self.hover_amount = amount
        if changed:
            self.update()

    def _scaled(self, path: Path):
        dpr = self.devicePixelRatioF()
        key = (path, self.width(), dpr)
        if key not in self._cache:
            src = QPixmap(str(path))
            if src.isNull():
                return None
            pm = src.scaled(int(self.width() * dpr), int(self.height() * dpr),
                            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
            pm.setDevicePixelRatio(dpr)
            self._cache[key] = pm
        return self._cache[key]

    # ---------------------------------------------------------------- size, place, settings
    def _apply_size(self) -> None:
        src = QPixmap(str(self.pack.image("idle", 0, False, False)))
        w = int(self.cfg["width"])
        h = round(w * src.height() / src.width()) if not src.isNull() and src.width() else w
        self.setFixedSize(w, h)

    def _screen(self):
        """The monitor the avatar was left on (by name), or the primary one when it is gone."""
        name = self.cfg.get("screen", "")
        for s in QGuiApplication.screens():
            if name and s.name() == name:
                return s
        return QGuiApplication.primaryScreen()

    def reposition(self) -> None:
        screen = self._screen()
        if screen is None:
            return
        g = screen.availableGeometry()
        area, size = (g.x(), g.y(), g.width(), g.height()), (self.width(), self.height())
        x, y = self._place(self.cfg["corner"], area, size)
        dx, dy = self.cfg.get("offset", [0, 0])
        self.move(*clamp((x + dx, y + dy), area, size))          # always fully on the screen, wherever it was dropped

    def on_screen_changed(self, *_args) -> None:
        self.reposition()

    def _save(self) -> None:
        save_config(self.cfg, self.config_path or CONFIG_PATH)

    def set_width(self, width: int) -> None:
        self.cfg["width"] = int(width)
        self._apply_size()
        self.reposition()
        self.update()
        self._save()

    def set_corner(self, corner: str) -> None:
        if corner in CORNERS:
            self.cfg["corner"], self.cfg["offset"] = corner, [0, 0]
            self.reposition()
            self._save()

    def set_opacity(self, opacity: float) -> None:
        self.cfg["opacity"] = float(opacity)
        self.update()
        self._save()

    def set_hover_radius(self, radius: int) -> None:
        self.cfg["hover_radius"] = int(radius)
        self.update()
        self._save()

    def set_pack(self, folder: Path) -> None:
        """Switch avatar. A pack that cannot be loaded leaves the current one in place and says why."""
        pack, error = load_pack_or_default(Path(folder), self.pack.folder)
        if error is not None:
            self.pack_error = error
            if self.tray:
                self.tray.setToolTip(error)
            return
        self.pack, self.pack_error = pack, None
        self.animator = Animator(self._rng or random.Random(), pack.blink_min, pack.blink_max, pack.blink_ms)
        self._cache.clear()
        self._path = pack.image("idle", 0, False, False)
        if pack.width:
            self.cfg["width"] = pack.width
        inside = Path(folder).resolve().is_relative_to(ROOT)
        self.cfg["pack"] = Path(folder).resolve().relative_to(ROOT).as_posix() if inside else str(folder)
        self._apply_size()
        self.reposition()
        self.refresh()
        self.update()
        if self.tray:
            self.tray.setIcon(QIcon(QPixmap(str(self._path))))
            self.tray.setToolTip("Claude avatar")
        self._save()

    def toggle_visible(self) -> None:
        self.cfg["visible"] = not self.isVisible()
        self.setVisible(self.cfg["visible"])
        self._save()

    # ---------------------------------------------------------------- move mode (drag to a new corner)
    def set_move_mode(self, on: bool) -> None:
        self._moving = on
        if self._move_action is not None and self._move_action.isChecked() != on:      # keep the menu tick honest
            self._move_action.blockSignals(True)
            self._move_action.setChecked(on)
            self._move_action.blockSignals(False)
        was_visible = self.isVisible()
        # Qt re-adds WindowTransparentForInput while WA_TransparentForMouseEvents is set, so change the attribute first
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not on)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, not on)
        if was_visible:
            self.show()                              # changing window flags hides the window

    def mousePressEvent(self, event) -> None:
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event) -> None:
        if self._drag_offset is not None:
            self.finish_drag()

    def finish_drag(self) -> None:
        """Keep the avatar exactly where it was dropped (on whichever monitor), then go back to click-through."""
        self._drag_offset = None
        screen = QGuiApplication.screenAt(self.geometry().center()) or self._screen()
        g = screen.availableGeometry()
        area, size = (g.x(), g.y(), g.width(), g.height()), (self.width(), self.height())
        pos = clamp((self.x(), self.y()), area, size)
        corner, (dx, dy) = anchor_from_position(pos, area, size)
        self.cfg.update(corner=corner, offset=[dx, dy], screen=screen.name())
        self.move(*pos)
        self._save()
        self.set_move_mode(False)

    # ---------------------------------------------------------------- tray menu
    def build_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("Show / Hide").triggered.connect(self.toggle_visible)
        avatar = menu.addMenu("Avatar")
        avatar.aboutToShow.connect(lambda: self._fill_avatar_menu(avatar))     # new pack folders show up without a restart
        self._fill_avatar_menu(avatar)
        corner = menu.addMenu("Corner")
        for c in CORNERS:
            corner.addAction(c.replace("-", " ").title()).triggered.connect(lambda _=False, c=c: self.set_corner(c))
        size = menu.addMenu("Size")
        for w in (120, 160, 220, 300):
            size.addAction(f"{w} px").triggered.connect(lambda _=False, w=w: self.set_width(w))
        opacity = menu.addMenu("Opacity")
        for pct in (50, 75, 100):
            opacity.addAction(f"{pct}%").triggered.connect(lambda _=False, pct=pct: self.set_opacity(pct / 100))
        see = menu.addMenu("See-through")
        for label, px in (("Off", 0), ("Small", 40), ("Medium", 60), ("Large", 90)):
            see.addAction(label).triggered.connect(lambda _=False, px=px: self.set_hover_radius(px))
        move = menu.addAction("Move mode")
        move.setCheckable(True)
        move.toggled.connect(self.set_move_mode)
        self._move_action = move
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(QApplication.quit)
        self._menu = menu
        return menu

    def _fill_avatar_menu(self, menu: QMenu) -> None:
        menu.clear()
        for p in discover_packs(self.packs_dir):
            action = menu.addAction(p.name)
            action.setCheckable(True)
            action.setChecked(p.folder.resolve() == self.pack.folder.resolve())
            action.triggered.connect(lambda _=False, folder=p.folder: self.set_pack(folder))

    def start(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(QPixmap(str(self.pack.image("idle", 0, False, False)))), self)
            self.tray.setContextMenu(self.build_menu())
            self.tray.setToolTip(self.pack_error or "Claude avatar")
            self.tray.show()
        self.timer.start()
        self.hover_timer.start()
        if self.cfg["visible"]:
            self.show()

    def release_lock(self) -> None:
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None


def create(config_path: Path | None = None, lock_path: Path | None = None, default_pack: Path = DEFAULT_PACK,
           state_path: Path | None = None) -> AvatarWindow | None:
    """Build the window, or return None when another copy is already running (every Claude session asks for one)."""
    lock_path = Path(lock_path or LOCK_PATH)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)                        # a lock left by a dead process is taken over at once
    if not lock.tryLock(0):
        return None
    window = AvatarWindow(load_config(config_path), state_path or ROOT / "state" / "avatar.json",
                          default_pack=default_pack, config_path=config_path)
    window._lock = lock
    return window


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = create()
    if window is None:
        return 0
    window.start()
    code = app.exec()
    window.release_lock()
    return code


if __name__ == "__main__":
    sys.exit(main())

