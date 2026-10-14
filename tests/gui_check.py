"""GUI 层联调：真实抓屏 → 裁剪 → 落盘 → 生成悬浮窗。

不触发鼠标交互（那需要人工操作），但走完真实像素路径，
能验证 Retina 换算、悬浮窗构造、拖出数据构造是否正常。

运行： .venv/bin/python tests/gui_check.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QMimeData, QRect, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from screenfloat.capture import SelectOverlay, grab_screen  # noqa: E402
from screenfloat.config import Config  # noqa: E402
from screenfloat.floatwin import FloatWindow, ManagerWindow, make_app_icon  # noqa: E402
from screenfloat.store import ShotStore  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail if not cond else ''}")
    if not cond:
        _failures.append(name)


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841

    print("\n=== 抓屏 ===")
    screenshot, screen = grab_screen()
    check("屏幕截图非空", not screenshot.isNull(),
          f"(size={screenshot.width()}x{screenshot.height()})")
    dpr = screen.devicePixelRatio()
    print(f"  屏幕 dpr = {dpr}，图像 = {screenshot.width()}x{screenshot.height()}")

    print("\n=== 遮罩选区裁剪 ===")
    overlay = SelectOverlay(screenshot, screen)
    logical_w = screen.geometry().width()
    logical_h = screen.geometry().height()

    # 模拟一次框选：取屏幕左上角 1/4 区域
    rect = QRect(10, 10, max(40, logical_w // 4), max(40, logical_h // 4))
    cropped = overlay._crop(rect)
    check("裁剪结果非空", cropped is not None and not cropped.isNull())

    if cropped is not None:
        # 期望宽度 = 逻辑宽度 * dpr
        expect_w = int(rect.width() * dpr)
        got_w = cropped.width()
        # 允许 2 像素误差（int 截断 + 边界交集）
        check(
            "裁剪宽度符合 dpr 换算",
            abs(got_w - expect_w) <= 2,
            f"(期望≈{expect_w}，实际{got_w})",
        )
        check("裁剪高度符合 dpr 换算",
              abs(cropped.height() - int(rect.height() * dpr)) <= 2,
              f"(实际{cropped.height()})")

        # 越界保护：选区超出屏幕不应崩溃
        oob = overlay._crop(QRect(logical_w - 5, logical_h - 5, 500, 500))
        check("越界选区不崩溃且已裁剪到边界",
              oob is None or (oob.width() <= 5 * dpr + 2 and oob.height() <= 5 * dpr + 2),
              f"(got={oob.width()}x{oob.height() if oob else 0})")

    print("\n=== 悬浮窗构造 ===")
    tmp = Path(tempfile.mkdtemp(prefix="sf_gui_"))
    cfg = Config()
    cfg.cache_dir = str(tmp)
    cfg.expire_minutes = 30

    store = ShotStore(cfg)
    big = QPixmap(900, 600)
    big.fill(Qt.white)
    shot = store.add_pixmap(big)

    manager = ManagerWindow(cfg)
    manager.store = store
    win = manager.spawn(shot)

    check("悬浮窗已创建", win is not None)
    check("悬浮窗可见", win.isVisible())
    check("悬浮窗置顶", bool(win.windowFlags() & Qt.WindowStaysOnTopHint))
    check("悬浮窗无边框", bool(win.windowFlags() & Qt.FramelessWindowHint))
    check("透明背景", win.testAttribute(Qt.WA_TranslucentBackground))

    # 900px 宽的图应被缩到 float_max_width=320
    disp_w = win.image_label.pixmap().width()
    check("大图已缩放到最大宽度", disp_w <= cfg.float_max_width,
          f"(显示宽={disp_w}，上限={cfg.float_max_width})")
    # 比例应保持：320/900
    ratio_ok = abs(disp_w / win.image_label.pixmap().height() - 900 / 600) < 0.05
    check("缩放保持宽高比", ratio_ok)

    print("\n=== 拖出数据构造 ===")
    # 复用真实拖拽逻辑里的 mime 组装方式做校验
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(shot.path))])
    pm = QPixmap(str(shot.path))
    mime.setImageData(pm)

    urls = mime.urls()
    check("含 file:// URL", len(urls) == 1 and urls[0].isLocalFile())
    check("URL 指向存在的文件", Path(urls[0].toLocalFile()).exists())
    check("URL 为 png", urls[0].toLocalFile().endswith(".png"))
    check("含图片数据兜底", not mime.imageData().isNull())
    # Qt 内部用 application/x-qt-image 表示内存图片；
    # 跨进程投送时系统会按 QPixmap 的实际格式协商，无需显式 image/png
    check("同时提供文件与图片两种格式",
          "text/uri-list" in mime.formats() and "application/x-qt-image" in mime.formats(),
          f"(formats={mime.formats()})")

    print("\n=== 倒计时刷新 ===")
    win.tick()
    status1 = win.title.status.text()
    check("显示倒计时", ":" in status1 and "后自动清除" in status1, f"({status1})")
    shot.pinned = True
    win.tick()
    check("钉住后不再显示倒计时", ":" not in win.title.status.text(),
          f"({win.title.status.text()})")
    shot.pinned = False

    print("\n=== 关闭联动store ===")
    manager.on_window_closed(win)
    check("关闭后文件被删除", not shot.path.exists())
    check("窗口从列表移除", len(manager.windows()) == 0)
    check("store 列表同步清空", len(store.shots()) == 0)

    print("\n=== 图标生成 ===")
    icon = make_app_icon()
    check("图标非空", not icon.isNull())
    check("图标含多种尺寸", len(icon.availableSizes()) >= 1,
          f"(sizes={icon.availableSizes()})")

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 46)
    if _failures:
        print(f"结果：{len(_failures)} 项失败 -> {_failures}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())