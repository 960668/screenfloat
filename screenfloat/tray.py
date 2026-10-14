"""菜单栏 / 系统托盘。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .config import Config

# 托盘菜单里可选的过期时长
TTL_PRESETS = [0, 10, 30, 60, 120]


def humanize_ttl(minutes: int) -> str:
    return "不自动清除" if minutes == 0 else f"{minutes} 分钟"


class TrayIcon(QObject):
    """封装托盘图标及其菜单。"""

    def __init__(self, icon, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._on_capture: Callable[[], None] = lambda: None
        self._on_clear: Callable[[], None] = lambda: None
        self._on_quit: Callable[[], None] = lambda: None
        self._on_ttl_change: Callable[[int], None] = lambda m: None

        self.tray = QSystemTrayIcon(icon, parent)
        self.tray.setToolTip("ScreenFloat · 截图悬浮缓存")

        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)

    # ------------------------------------------------------------------ 菜单

    def _build_menu(self) -> None:
        m = self.menu
        m.clear()

        cap = QAction("立即截图", m)
        cap.triggered.connect(lambda: self._on_capture())
        m.addAction(cap)

        m.addSeparator()

        self.ttl_menu = QMenu("自动清除时长", m)
        self._rebuild_ttl_menu()
        m.addMenu(self.ttl_menu)

        reveal = QAction("打开缓存文件夹", m)
        reveal.triggered.connect(self._open_folder)
        m.addAction(reveal)

        clear = QAction("清空全部截图", m)
        clear.triggered.connect(lambda: self._on_clear())
        m.addAction(clear)

        m.addSeparator()
        quit_action = QAction("退出 ScreenFloat", m)
        quit_action.triggered.connect(lambda: self._on_quit())
        m.addAction(quit_action)

    def _rebuild_ttl_menu(self) -> None:
        self.ttl_menu.clear()
        for minutes in TTL_PRESETS:
            act = QAction(humanize_ttl(minutes), self.ttl_menu)
            act.setCheckable(True)
            act.setChecked(self.config.expire_minutes == minutes)
            act.triggered.connect(
                lambda _checked=False, m=minutes: self._set_ttl(m)
            )
            self.ttl_menu.addAction(act)

    def _set_ttl(self, minutes: int) -> None:
        self.config.expire_minutes = minutes
        self.config.save()
        self._rebuild_ttl_menu()
        self._on_ttl_change(minutes)

    def _open_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        d = Path(self.config.cache_path)
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _on_activated(self, reason) -> None:
        # macOS 上左键点击直接触发截图，减少一次菜单点击
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._on_capture()

    # ------------------------------------------------------------------ 回调

    def bind(
        self,
        on_capture: Callable[[], None],
        on_clear: Callable[[], None],
        on_quit: Callable[[], None],
        on_ttl_change: Callable[[int], None],
    ) -> None:
        self._on_capture = on_capture
        self._on_clear = on_clear
        self._on_quit = on_quit
        self._on_ttl_change = on_ttl_change

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, self.tray.icon(), 2500)

    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()