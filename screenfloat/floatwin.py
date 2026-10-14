"""悬浮截图卡片。

关键交互：
- 图片区域按下并拖动 → 以「文件 + 图片」双格式投送到外部应用（微信/QQ 等）
- 顶部标题条拖动 → 移动窗口本身
- 双击图片 → 复制到剪贴板
- 右上角按钮 → 钉住（不过期）/ 关闭（删文件）

拖出用 QDrag + QMimeData：既带上 file:// URL 让接收方当成真实文件
处理（发出去的是图片文件，能存原图），也带上 imageData 兜底，
应付只认内存图片的应用。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDrag, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import shiboken6

from .config import Config
from .store import Shot

TITLE_BAR_HEIGHT = 28
CARD_PADDING = 6
CORNER_RADIUS = 10


def make_app_icon() -> QIcon:
    """程序图标：画一个带取景框的相机符号，避免依赖外部资源文件。"""
    coral = QColor("#FF5A5F")
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(coral)
    p.drawRoundedRect(QRect(4, 14, 56, 40), 10, 10)
    p.setBrush(QColor("#FFD166"))
    p.drawRoundedRect(QRect(20, 6, 24, 14), 5, 5)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QRect(20, 24, 24, 24))
    p.setBrush(coral)
    p.drawEllipse(QRect(27, 31, 10, 10))
    p.end()
    return QIcon(pm)


class ImageLabel(QLabel):
    """显示截图，并承担「拖出到外部应用」的逻辑。"""

    # 拖动超过这个距离（逻辑像素）才判定为拖拽，避免和点击混淆
    DRAG_THRESHOLD = 6

    def __init__(self, shot: Shot, parent: QWidget) -> None:
        super().__init__(parent)
        self.shot = shot
        self._press_pos: QPoint | None = None
        self._dragging = False
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.OpenHandCursor)

    def set_pixmap(self, pm: QPixmap, max_width: int) -> None:
        """按最大宽度等比缩放显示，并同步控件尺寸。"""
        if pm.isNull():
            return
        scaled = pm
        if pm.width() > max_width:
            scaled = pm.scaledToWidth(max_width, Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self.setFixedSize(scaled.size())

    # ------------------------------------------------------------ 拖拽投送

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._press_pos = ev.position().toPoint()
            self._dragging = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev) -> None:
        if self._press_pos is None or not (ev.buttons() & Qt.LeftButton):
            return
        delta = ev.position().toPoint() - self._press_pos
        if not self._dragging and (delta.manhattanLength() > self.DRAG_THRESHOLD):
            self._dragging = True
            self._start_drag()

        if self._dragging:
            # 拖出后把鼠标交回系统，后续 move 事件不需要再处理
            self._press_pos = None

    def mouseReleaseEvent(self, ev) -> None:
        self._press_pos = None
        if not self._dragging:
            return
        self._dragging = False
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, ev) -> None:
        QGuiApplication.clipboard().setImage(QPixmap(str(self.shot.path)))

    def _start_drag(self) -> None:
        """构造拖拽数据并投送到外部应用。

        注意：QDrag.exec 会进入嵌套事件循环直到用户松开，
        因此这里返回后 Qt 已经完成了这次跨应用拖放。
        """
        path = Path(self.shot.path)
        if not path.exists():
            return

        mime = QMimeData()
        # 1) 作为真实文件投送：接收方能拿到原图文件
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        # 2) 内存图片兜底：应对只接受 image/* 的应用
        pm = QPixmap(str(path))
        if not pm.isNull():
            mime.setImageData(pm)

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.pixmap().scaledToWidth(120, Qt.SmoothTransformation))
        drag.setHotSpot(QPoint(20, 20))
        drag.exec(Qt.CopyAction)


class TitleBar(QFrame):
    """标题条：拖动移动窗口 + 右侧按钮。"""

    def __init__(self, window: "FloatWindow") -> None:
        super().__init__(window)
        self._win = window
        self._press_pos: QPoint | None = None
        self._drag_offset: QPoint | None = None

        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(28, 28, 30, 235);
                border-top-left-radius: {CORNER_RADIUS}px;
                border-top-right-radius: {CORNER_RADIUS}px;
            }}
            QLabel {{
                color: #F2F2F7;
                font-size: 11px;
                padding-left: 8px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                color: #C7C7CC;
                font-size: 12px;
                padding: 0 6px;
                min-width: 20px;
            }}
            QPushButton:hover {{ color: #FFFFFF; }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(2)

        self.status = QLabel("30 分钟后自动清除")
        self.status.setObjectName("statusLabel")
        layout.addWidget(self.status)
        layout.addStretch(1)

        self.pin_btn = self._make_button("📌")
        self.copy_btn = self._make_button("⧉")
        self.close_btn = self._make_button("✕")
        layout.addWidget(self.pin_btn)
        layout.addWidget(self.copy_btn)
        layout.addWidget(self.close_btn)

        self.pin_btn.clicked.connect(self._win.toggle_pin)
        self.copy_btn.clicked.connect(self._win.copy_to_clipboard)
        self.close_btn.clicked.connect(self._win.dismiss)

    def _make_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        return btn

    # ------------------------------------------------------------ 移动窗口

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._press_pos = ev.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev) -> None:
        if self._press_pos is None or not (ev.buttons() & Qt.LeftButton):
            return
        self._win.move(ev.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, ev) -> None:
        self._press_pos = None


class FloatWindow(QFrame):
    """一张截图对应一个悬浮窗。"""

    def __init__(self, shot: Shot, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.shot = shot
        self.config = config
        shot.window = self

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.title = TitleBar(self)
        outer.addWidget(self.title)

        holder = QFrame()
        holder.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(28, 28, 30, 245);
                border-bottom-left-radius: {CORNER_RADIUS}px;
                border-bottom-right-radius: {CORNER_RADIUS}px;
            }}
            """
        )
        bl = QVBoxLayout(holder)
        bl.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)

        self.image_label = ImageLabel(shot, holder)
        bl.addWidget(self.image_label)
        outer.addWidget(holder)

        pm = QPixmap(str(shot.path))
        self.image_label.set_pixmap(pm, config.float_max_width)
        self.adjustSize()
        self._refresh_status()

    # ------------------------------------------------------------------ 状态

    def _refresh_status(self) -> None:
        ttl = self.config.expire_minutes
        if self.shot.pinned:
            self.title.status.setText("已钉住 · 不会自动清除")
        elif ttl <= 0:
            self.title.status.setText("不自动清除")
        else:
            self.title.status.setText(f"{ttl} 分钟后自动清除")

    def tick(self) -> None:
        """由巡检定时器驱动，刷新标题栏的剩余时间提示。"""
        if self.shot.pinned:
            # 钉住后倒计时已失效，需要改回「不会自动清除」的文案
            if "钉住" not in self.title.status.text():
                self._refresh_status()
            return
        ttl = self.config.expire_seconds
        if ttl <= 0:
            if "不自动清除" not in self.title.status.text():
                self._refresh_status()
            return
        left = max(0, int(ttl - self.shot.age_seconds))
        mins, secs = divmod(left, 60)
        self.title.status.setText(f"{mins:02d}:{secs:02d} 后自动清除")

    # ------------------------------------------------------------------ 动作

    def toggle_pin(self) -> None:
        self.shot.pinned = not self.shot.pinned
        self._refresh_status()

    def copy_to_clipboard(self) -> None:
        QGuiApplication.clipboard().setImage(QPixmap(str(self.shot.path)))
        self.title.copy_btn.setText("✓")
        QTimer.singleShot(1200, lambda: self.title.copy_btn.setText("⧉"))

    def dismiss(self) -> None:
        """用户手动关闭：通知 app 层走 store 清理逻辑。"""
        win = self.window()
        win.on_window_closed(self)

    def closeEvent(self, ev) -> None:
        # 用户直接关窗（⌘W 等）也要走同一条清理链路
        if self.shot.window is self:
            parent = self.window()
            if hasattr(parent, "on_window_closed") and parent is not self:
                parent.on_window_closed(self)
                ev.ignore()
                return
        ev.accept()


class ManagerWindow(QWidget):
    """隐藏的宿主窗口，用来聚合所有悬浮卡片。

    没有它的话，每张截图都是一个顶层窗口，托盘菜单和清理回调不好挂。
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._windows: list[FloatWindow] = []
        self._cascade = 0

    def spawn(self, shot: Shot) -> FloatWindow:
        win = FloatWindow(shot, self.config, parent=self)
        # 多张截图时右下角错位排开，避免完全重叠
        offset = (self._cascade % 6) * 26
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 1440, 900)
        x = geo.right() - win.width() - 40 - offset
        y = geo.bottom() - win.height() - 40 - offset
        win.move(max(geo.left(), x), max(geo.top(), y))
        self._cascade += 1

        win.show()
        win.raise_()
        self._windows.append(win)
        return win

    def windows(self) -> list[FloatWindow]:
        """返回仍然有效的悬浮窗。

        必须用 shiboken6.isValid 判断，而不能只判断 `is not None`：
        PySide6 的 widget 被销毁后，Python 引用还在，但 C++ 对象已没了，
        访问它的任何方法都会抛
        `RuntimeError: Internal C++ object already deleted`。
        这个坑曾导致定时器刷新倒计时崩溃、程序静默退出。
        """
        alive = []
        for w in self._windows:
            try:
                if shiboken6.isValid(w):
                    alive.append(w)
            except (RuntimeError, TypeError):
                continue
        # 顺带清理失效引用，避免列表无限增长
        self._windows = alive
        return alive

    def on_window_closed(self, win: FloatWindow) -> None:
        """悬浮窗请求关闭：交给 store 删文件，并移除窗口。"""
        from .store import ShotStore

        store: ShotStore | None = getattr(self, "store", None)
        # 窗口可能已被 C++ 侧销毁，此时取 shot 会抛 RuntimeError
        try:
            shot = win.shot
        except RuntimeError:
            shot = None

        if store is not None and shot is not None:
            store.remove(shot)
        elif shiboken6.isValid(win):
            win.close()

        try:
            self._windows.remove(win)
        except ValueError:
            pass

    def close_all(self) -> None:
        for win in list(self._windows):
            try:
                if shiboken6.isValid(win):
                    win.close()
            except RuntimeError:
                continue
        self._windows.clear()

    def tick_all(self) -> None:
        """刷新所有悬浮窗的倒计时。失效窗口会被自动跳过。"""
        for win in self.windows():
            try:
                win.tick()
            except RuntimeError:
                # 窗口在 tick 过程中被销毁，跳过即可
                continue