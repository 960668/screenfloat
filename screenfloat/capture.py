"""全屏截图与框选遮罩。

流程：
1. 用 Qt 抓取屏幕像素（自动按屏幕的 devicePixelRatio 处理 Retina）。
2. 铺一层全屏暗化遮罩窗口，把原图作为背景画上去。
3. 用户拖拽出选区，实时显示尺寸提示；Esc 取消，回车或松开鼠标确认。
4. 从原始截图中裁剪选区返回，避免二次缩放损失画质。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

# 遮罩暗化程度：0 = 完全透明（不遮），255 = 全黑
DIM_ALPHA = 120
BORDER_COLOR = QColor("#4C8DFF")
BORDER_WIDTH = 2
HANDLE_SIZE = 8
HINT_BG = QColor(0, 0, 0, 200)


def grab_screen(screen=None) -> tuple[QPixmap, object]:
    """抓取整屏像素，返回 (像素图, 屏幕对象)。

    grabWindow(0) 在 macOS 上抓的是全屏；在部分平台上需要传 winId，
    0 代表「整个屏幕」这一约定各平台通用。
    """
    screen = screen or QGuiApplication.primaryScreen()
    pm = screen.grabWindow(0)
    return pm, screen


class SelectOverlay(QWidget):
    """全屏暗化遮罩，负责框选。"""

    selected = Signal(QPixmap)
    cancelled = Signal()

    def __init__(self, screenshot: QPixmap, screen, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shot = screenshot
        self._screen = screen
        self._origin: QPoint | None = None
        self._current: QPoint | None = None

        self.setCursor(QCursor(Qt.CrossCursor))
        self.setMouseTracking(True)
        # 无边框、置顶、覆盖全屏
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        # 必须透明：选区要用 Clear 模式「擦亮」，需要窗口支持 alpha 通道
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setGeometry(screen.geometry())

    # ------------------------------------------------------------------ 选择

    def _selection_rect(self) -> QRect | None:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    # ------------------------------------------------------------------ 事件

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.LeftButton:
            pos = ev.position().toPoint()
            self._origin = pos
            self._current = pos
            self.update()
        elif ev.button() == Qt.RightButton:
            self.cancelled.emit()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._origin is None:
            return
        self._current = ev.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if ev.button() != Qt.LeftButton:
            return
        rect = self._selection_rect()
        # 太小的选区视为误触，直接取消
        if rect is None or rect.width() < 4 or rect.height() < 4:
            self.cancelled.emit()
            return

        pixmap = self._crop(rect)
        self.cancelled.emit()  # 先解除遮罩
        if pixmap is not None:
            self.selected.emit(pixmap)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() == Qt.Key_Escape:
            self.cancelled.emit()
        elif ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            rect = self._selection_rect()
            if rect and rect.width() >= 4 and rect.height() >= 4:
                pixmap = self._crop(rect)
                self.cancelled.emit()
                if pixmap is not None:
                    self.selected.emit(pixmap)

    # ------------------------------------------------------------------ 裁剪

    def _crop(self, rect: QRect) -> QPixmap | None:
        """从原始截图裁剪选区。

        遮罩窗口坐标是逻辑像素，截图像素是设备像素（Retina 下 2 倍），
        这里乘上比例换算，避免裁出来的图只拿到一半。
        """
        dpr = self._screen.devicePixelRatio() if self._screen else 1.0
        pm = self._shot
        if pm.isNull():
            return None

        dev = QRect(
            int(rect.x() * dpr),
            int(rect.y() * dpr),
            int(rect.width() * dpr),
            int(rect.height() * dpr),
        )
        # 与图片实际边界求交集，防止多屏或边缘越界
        dev = dev.intersected(QRect(0, 0, pm.width(), pm.height()))
        if dev.width() <= 0 or dev.height() <= 0:
            return None

        cropped = pm.copy(dev)
        cropped.setDevicePixelRatio(dpr)
        return cropped

    # ------------------------------------------------------------------ 绘制

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._shot)

        rect = self._selection_rect()
        if rect is None:
            # 未开始框选：整屏均匀压暗 + 提示文案
            p.fillRect(self.rect(), QColor(0, 0, 0, DIM_ALPHA))
            self._draw_crosshair_hint(p)
            p.end()
            return

        # 有选区时：只把选区**四周**压暗，选区本身保持原亮度。
        # 这里刻意不用 CompositionMode_Clear——它在透明窗口上配合
        # fillRect 容易出坑，而且逐帧清屏会有闪烁；
        # 画四个矩形留白既直观又稳定。
        self._dim_around_selection(p, rect)

        p.setPen(QPen(BORDER_COLOR, BORDER_WIDTH))
        p.drawRect(rect.adjusted(0, 0, -1, -1))

        self._draw_handles(p, rect)
        self._draw_size_hint(p, rect)
        p.end()

    def _dim_around_selection(self, p: QPainter, sel: QRect) -> None:
        """把选区以外的区域压暗，选区保持原样。"""
        full = self.rect()
        dim = QColor(0, 0, 0, DIM_ALPHA)

        # 与选区相交后的有效区域（选区可能被拖到窗口外）
        area = sel.intersected(full)
        if area.isEmpty():
            p.fillRect(full, dim)
            return

        # 上
        p.fillRect(QRect(full.left(), full.top(), full.width(), area.top() - full.top()), dim)
        # 下
        p.fillRect(
            QRect(full.left(), area.bottom() + 1, full.width(), full.bottom() - area.bottom()),
            dim,
        )
        # 左
        p.fillRect(QRect(full.left(), area.top(), area.left() - full.left(), area.height()), dim)
        # 右
        p.fillRect(
            QRect(area.right() + 1, area.top(), full.right() - area.right(), area.height()),
            dim,
        )

    def _draw_crosshair_hint(self, p: QPainter) -> None:
        f = QFont()
        f.setPointSize(13)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        text = "拖拽鼠标框选要截取的区域 · Esc 取消"
        p.drawText(self.rect(), Qt.AlignCenter, text)

    def _draw_handles(self, p: QPainter, rect: QRect) -> None:
        p.setBrush(BORDER_COLOR)
        p.setPen(Qt.NoPen)
        for pt in (
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight(),
        ):
            p.drawRect(
                QRect(pt.x() - HANDLE_SIZE // 2, pt.y() - HANDLE_SIZE // 2, HANDLE_SIZE, HANDLE_SIZE)
            )

    def _draw_size_hint(self, p: QPainter, rect: QRect) -> None:
        label = f"{rect.width()} × {rect.height()}"
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)

        metrics = p.fontMetrics()
        tw = metrics.horizontalAdvance(label) + 14
        th = metrics.height() + 8

        # 提示条优先放在选区下方，越界时翻到上方
        bx = rect.x() + rect.width() // 2 - tw // 2
        by = rect.bottom() + 8
        if by + th > self.height():
            by = rect.y() - th - 8

        box = QRect(bx, max(0, by), tw, th)
        p.setPen(Qt.NoPen)
        p.setBrush(HINT_BG)
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(box, Qt.AlignCenter, label)


def capture_region(screen=None) -> tuple[QPixmap | None, object]:
    """执行一次「全屏 → 框选」，返回裁剪结果与原屏幕对象。

    采用阻塞式事件循环：遮罩显示期间只跑遮罩自己，
    用户确认或取消后返回，避免和主窗口事件循环互相干扰。
    """
    from PySide6.QtCore import QEventLoop

    screenshot, the_screen = grab_screen(screen)
    if screenshot.isNull():
        return None, the_screen

    overlay = SelectOverlay(screenshot, the_screen)
    result: dict[str, QPixmap] = {}

    loop = QEventLoop()
    overlay.selected.connect(lambda pm: (result.update(pixmap=pm), loop.quit()))
    overlay.cancelled.connect(loop.quit)
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    overlay.setFocus()

    loop.exec()
    overlay.close()
    overlay.deleteLater()

    return result.get("pixmap"), the_screen