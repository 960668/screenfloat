"""主控制面板。

存在的意义：给截图功能一个不依赖全局热键的入口。
即使 macOS 因权限或环境原因收不到全局按键，这里仍能正常截图。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, Qt as QGuiQt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ControlPanel(QWidget):
    """一个极简控制窗：显示状态 + 截图按钮。"""

    def __init__(
        self,
        on_capture: Callable[[], None],
        on_quit: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_capture = on_capture
        self._on_quit = on_quit

        self.setWindowTitle("ScreenFloat · 截图悬浮缓存")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("ScreenFloat")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(title)

        desc = QLabel(
            "截图会自动悬浮在桌面，\n"
            "存进本地缓存，30 分钟后自动清除。\n\n"
            "悬浮窗里的图片可直接拖进聊天窗口。"
        )
        desc.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(desc)

        layout.addSpacing(6)

        self.capture_btn = QPushButton("开始截图")
        self.capture_btn.setFixedHeight(38)
        self.capture_btn.setStyleSheet(
            """
            QPushButton {
                background: #4C8DFF; color: white;
                border: none; border-radius: 8px;
                font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #3B7AE8; }
            QPushButton:pressed { background: #2F66CC; }
            """
        )
        self.capture_btn.clicked.connect(self._handle_capture)
        layout.addWidget(self.capture_btn)

        self.hint = QLabel("点击后拖拽框选区域")
        self.hint.setStyleSheet("color: #999; font-size: 11px;")
        self.hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.hint)

        # 热键不可用时才显示，默认隐藏
        self.warn = QLabel()
        self.warn.setVisible(False)
        layout.addWidget(self.warn)

        layout.addStretch(1)

        quit_btn = QPushButton("退出程序")
        quit_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            "color: #999; font-size: 12px; }"
            "QPushButton:hover { color: #4C8DFF; }"
        )
        quit_btn.clicked.connect(self._on_quit)
        layout.addWidget(quit_btn)

    def _handle_capture(self) -> None:
        # 截图时先隐藏自己，避免把控制窗也框进选区；
        # capture() 会在结束后重新显示
        self.hide()
        try:
            self._on_capture()
        finally:
            self.show()
            self.raise_()

    def install_fallback_shortcut(self, seq: QKeySequence) -> None:
        """全局热键不可用时的窗口级回退快捷键。"""
        action = QAction(self)
        action.setShortcut(seq)
        action.triggered.connect(self._handle_capture)
        self.addAction(action)
        self._fallback_action = action

    def show_permission_hint(self, reason: str = "") -> None:
        """热键不可用时，在面板上给出明确的修复指引。"""
        self.hint.setStyleSheet("color: #C8791A; font-size: 11px;")
        self.hint.setText("全局快捷键暂不可用 · 点击按钮截图不受影响")

        self.warn.setText(
            "如需全局快捷键，授权后重启程序：\n"
            "系统设置 → 隐私与安全性 → 输入监控 → 勾选 ScreenFloat"
        )
        self.warn.setVisible(True)