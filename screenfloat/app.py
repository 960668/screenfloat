"""程序入口：装配配置、托盘、截图、悬浮窗与定时清理。"""

from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QLockFile, QTimer, Qt
from PySide6.QtWidgets import QApplication

from .capture import capture_region
from .config import CONFIG_DIR, Config
from .floatwin import ManagerWindow, make_app_icon
from .hotkey import GlobalHotkey, input_monitoring_allowed, qkeysequence_for
from .panel import ControlPanel
from .store import ShotStore
from .tray import TrayIcon, humanize_ttl

# 倒计时刷新频率：1 秒一次，让用户看到「还剩多少」
TICK_INTERVAL_MS = 1_000

# 单实例锁：避免双击多次启动出多个托盘图标和重复热键
LOCK_TIMEOUT_MS = 200

# 陈旧锁容忍时长：进程消失（崩溃/强杀）后，锁文件残留超过这个时间即视为失效
STALE_LOCK_MS = 30_000


class _AlreadyRunning(Exception):
    """已有实例在运行，本次启动应当安静退出。"""


class ScreenFloatApp:
    """把各模块粘起来的应用对象。"""

    def __init__(self, argv: list[str]) -> None:
        # 先抢单实例锁，再创建 QApplication——
        # 顺序反了会先撞上 Qt 的单例限制，拿不到我们自己的锁判断
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(CONFIG_DIR / "screenfloat.lock"))
        # 允许清理「进程已不存在」的陈旧锁：程序崩溃或被强杀后锁文件会残留，
        # 若永不清理，用户之后每次双击都会被判为「已在运行」而毫无反应。
        # 设 0 表示关闭自动清理，故这里给一个明确的容忍窗口。
        self._lock.setStaleLockTime(STALE_LOCK_MS)
        if not self._lock.tryLock(LOCK_TIMEOUT_MS):
            raise _AlreadyRunning()

        self.qt = QApplication(argv)
        self.qt.setApplicationName("ScreenFloat")
        self.qt.setQuitOnLastWindowClosed(False)

        self.config = Config.load()
        self.icon = make_app_icon()
        self.qt.setWindowIcon(self.icon)

        self.store = ShotStore(self.config)
        self.manager = ManagerWindow(self.config)
        # 回填引用，让悬浮窗能回调到 store 做清理
        self.manager.store = self.store

        self.tray = TrayIcon(self.icon, self.config)
        self.tray.bind(
            on_capture=self.capture,
            on_clear=self.clear_all,
            on_quit=self.quit,
            on_ttl_change=self._on_ttl_change,
        )
        self.tray.show()

        # 独立的主控制窗口：即使全局热键失效，这里也能点「截图」，
        # 且窗口存在时可直接用系统快捷键 Cmd+Shift+S
        self.panel = ControlPanel(self.capture, self.quit)
        self.panel.show()

        self.hotkey = GlobalHotkey(self.config.hotkey, self.capture)
        self._hotkey_ok = self.hotkey.register()

        # 全局热键不可用时，退回窗口级快捷键（窗口聚焦时可用）
        if not self._hotkey_ok:
            seq = qkeysequence_for(self.config.hotkey)
            if seq is not None:
                self.panel.install_fallback_shortcut(seq)

        # 清理巡检 + 倒计时刷新共用一个定时器
        self.ticker = QTimer()
        self.ticker.setInterval(TICK_INTERVAL_MS)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start()

        # 诊断日志：排查「按了快捷键没反应」时把这些行发给我即可
        print(f"[ScreenFloat] 热键注册: {self._hotkey_ok} "
              f"| backend={self.hotkey.backend} "
              f"| error={self.hotkey.error or '(无)'}", flush=True)
        print(f"[ScreenFloat] 缓存目录: {self.config.cache_path}", flush=True)
        print(f"[ScreenFloat] 可监听全局按键: {input_monitoring_allowed()}", flush=True)

        self._restore_and_sweep()
        self._report_hotkey_status()

    # ------------------------------------------------------------------ 启动

    def _restore_and_sweep(self) -> None:
        """启动时清理过期文件，并把仍然新鲜的截图重新悬浮出来。"""
        restored = self.store.sweep_startup()
        for shot in restored:
            try:
                self.manager.spawn(shot)
            except Exception:
                # 单张恢复失败不影响其他
                continue

        if restored:
            self.tray.notify(
                "ScreenFloat",
                f"已恢复 {len(restored)} 张未过期截图",
            )

    def _report_hotkey_status(self) -> None:
        if self._hotkey_ok:
            return

        # 全局热键不可用：面板上给明确指引，同时弹一次通知
        self.panel.show_permission_hint(self.hotkey.error)
        reason = self.hotkey.error or "未知原因"
        print(f"[ScreenFloat] 全局快捷键不可用：{reason}", flush=True)
        self.tray.notify(
            "ScreenFloat · 快捷键未生效",
            f"{reason}。点击控制面板按钮仍可截图。",
        )

    # ------------------------------------------------------------------ 截图

    def capture(self) -> None:
        """执行一次截图 → 落盘 → 生成悬浮卡片。

        只负责隐藏已有的悬浮卡片（避免框选时把它们拍进去）；
        控制面板是否隐藏由调用方决定。
        """
        print("[ScreenFloat]收到截图请求，开始抓屏", flush=True)
        # 截图期间先藏起悬浮窗，避免把它们也截进去
        visible = self.manager.windows()
        for w in visible:
            w.hide()

        pixmap, _screen = capture_region()
        for w in visible:
            w.show()
            w.raise_()

        if pixmap is None or pixmap.isNull():
            print("[ScreenFloat] 已取消截图", flush=True)
            return  # 用户按 Esc 取消

        try:
            shot = self.store.add_pixmap(pixmap)
        except Exception as exc:
            self.tray.notify("ScreenFloat · 截图保存失败", str(exc))
            return

        self.manager.spawn(shot)
        print(f"[ScreenFloat] 截图已保存: {shot.path}", flush=True)

    # ------------------------------------------------------------------ 清理

    def _tick(self) -> None:
        # 到点自动清除：store 会删文件并关掉对应悬浮窗
        self.store.sweep()
        self.manager.tick_all()

    def clear_all(self) -> None:
        self.store.clear_all()
        self.tray.notify("ScreenFloat", "已清空全部截图")

    def _on_ttl_change(self, minutes: int) -> None:
        self.tray.notify(
            "ScreenFloat",
            f"自动清除时长已设为：{humanize_ttl(minutes)}",
        )
        # 时长变了，立刻重新巡检一次
        self.store.sweep()

    # ------------------------------------------------------------------ 退出

    def quit(self) -> None:
        self.hotkey.unregister()
        self.store.stop()
        self.ticker.stop()
        self.panel.close()
        self.tray.hide()
        self._lock.unlock()
        self.qt.quit()

    def run(self) -> int:
        return self.qt.exec()


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    try:
        app = ScreenFloatApp(argv)
    except _AlreadyRunning:
        # 已有实例在跑：不要静默退出——那会表现为「双击没反应」。
        # 改为提醒用户去菜单栏找图标，并正常返回。
        print("[ScreenFloat] 已在运行，请查看菜单栏图标", flush=True)
        _notify_already_running()
        return 0
    return app.run()


def _notify_already_running() -> None:
    """提示用户程序已在运行。失败也不影响，静默跳过。"""
    try:
        osascript_cmd = (
            'display notification "程序已在运行，请点菜单栏图标使用" '
            'with title "ScreenFloat"'
        )
        subprocess.run(
            ["osascript", "-e", osascript_cmd],
            timeout=5,
            capture_output=True,
        )
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())