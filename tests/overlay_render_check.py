"""截图遮罩绘制测试。

复现并验证修复：`fillRect(rect, 0, 0, 0, 255)` 这个重载在 PySide6 中不存在，
导致 paintEvent 每帧抛TypeError，框选痕迹完全看不见、
遮罩还会引发「QBackingStore::endPaint() called with active painter」。

运行： .venv/bin/python tests/overlay_render_check.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from screenfloat.capture import SelectOverlay  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail if not cond else ''}")
    if not cond:
        _failures.append(name)


class _FakeScreen:
    """最小可用的假屏幕对象。"""

    def __init__(self, w=800, h=600, dpr=1.0):
        self._w, self._h, self._dpr = w, h, dpr

    def geometry(self):
        return QRect(0, 0, self._w, self._h)

    def devicePixelRatio(self):
        return self._dpr


def render(overlay: SelectOverlay, w: int, h: int):
    """在离屏 QPixmap 上触发 paintEvent，捕获异常。"""
    pm = QPixmap(w, h)
    pm.fill(_transparent())
    p = QPainter(pm)
    try:
        # render(QPainter) 必须同时给 targetOffset，否则类型不匹配
        overlay.render(p, QPoint(0, 0))
        p.end()
        return None
    except Exception as exc:  # noqa: BLE001
        p.end()
        return exc


def _transparent():
    from PySide6.QtCore import Qt

    return Qt.transparent


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841

    screen = _FakeScreen(800, 600, 2.0)
    shot = QPixmap(1600, 1200)  # dpr=2 → 设备像素是逻辑的 2 倍
    shot.fill(QColor("#3366AA"))
    shot.setDevicePixelRatio(2.0)

    overlay = SelectOverlay(shot, screen)
    print("\n=== 基础状态 ===")
    check("遮罩创建成功", overlay is not None)
    check("透明背景已启用", overlay.testAttribute(__import__(
        "PySide6.QtCore", fromlist=["Qt"]).Qt.WA_TranslucentBackground))
    check("覆盖整个屏幕", overlay.geometry() == screen.geometry(),
          f"(got {overlay.geometry()})")

    print("\n=== paintEvent 绘制（未框选）===")
    err = render(overlay, 800, 600)
    check("未框选时绘制不抛异常", err is None, f"({type(err).__name__}: {err})")

    print("\n=== paintEvent 绘制（框选中）—— 关键场景 ===")
    overlay._origin = QPoint(100, 80)
    overlay._current = QPoint(400, 300)
    err = render(overlay, 800, 600)
    check("框选时绘制不抛异常", err is None, f"({type(err).__name__}: {err})")

    print("\n=== 各种边界选区 ===")
    cases = [
        ("左上角", QRect(0, 0, 10, 10)),
        ("贴右边界", QRect(780, 580, 20, 20)),
        ("超出右边界", QRect(700, 300, 300, 200)),
        ("完全超出屏幕", QRect(900, 700, 100, 100)),
        ("全屏", QRect(0, 0, 800, 600)),
        ("负坐标", QRect(-50, -50, 200, 200)),
        ("细长条", QRect(100, 100, 500, 2)),
    ]
    for label, r in cases:
        overlay._origin = r.topLeft()
        overlay._current = r.bottomRight()
        err = render(overlay, 800, 600)
        check(f"{label} 选区绘制正常", err is None, f"({err})")

    print("\n=== 拖动过程连续渲染 ===")
    errs = []
    for step in range(15):
        x = 50 + step * 30
        overlay._origin = QPoint(50, 50)
        overlay._current = QPoint(x, 50 + step * 20)
        e = render(overlay, 800, 600)
        if e:
            errs.append(f"step{step}: {e}")
    check("连续拖动 15 帧全部正常", not errs, f"({errs[:2]})")

    print("\n=== Retina 裁剪换算（dpr=2）===")
    overlay._origin = QPoint(100, 100)
    overlay._current = QPoint(300, 250)
    rect = overlay._selection_rect()
    cropped = overlay._crop(rect)
    check("裁剪成功", cropped is not None and not cropped.isNull())
    if cropped:
        expect_w = int(rect.width() * 2.0)
        check("宽度按 dpr=2 换算", abs(cropped.width() - expect_w) <= 2,
              f"(期望≈{expect_w}，实际{cropped.width()})")

    print("\n" + "=" * 46)
    if _failures:
        print(f"结果：{len(_failures)} 项失败 -> {_failures}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())