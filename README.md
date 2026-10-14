# ScreenFloat · 截图悬浮缓存

截图不用再手动保存。按下快捷键 → 框选 → 图片以悬浮卡片留在桌面，
自动存进本地缓存目录，30 分钟后自动清除，**直接把图片拖进聊天窗口就能发出去**。

![流程](https://img.shields.io/badge/流程-快捷键→框选→悬浮→拖走-blue)

macOS · Python 3.13 · PySide6

---

## 特性

- **截图即悬浮**：截完立刻以卡片形式留在桌面，不打断工作流
- **自动清理**：默认 30 分钟后自动删除，可在菜单栏改时长
- **拖进聊天窗口**：悬浮卡片可直接拖到微信/QQ/邮件，拿到原图文件而非压缩图
- **零权限打扰的快捷键**：基于 `CGEventTap`，只需授权「输入监控」
- **异常退出不丢图**：重启后自动恢复未过期的截图

## 安装

```bash
git clone https://github.com/960668/screenfloat.git
cd screenfloat

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 生成可双击运行的 .app（不弹终端窗口）
./build_app.sh --install
```

完成后 ScreenFloat.app 位于 `/Applications`，双击即可运行。

只想先试试、不打包：

```bash
.venv/bin/python -m screenfloat
```

### 首次使用需要授权

macOS 对截图类应用有隐私保护。首次使用请在：

**系统设置 → 隐私与安全性 → 屏幕与系统音频录制** 中勾选 ScreenFloat

授权后**完全退出程序再重新打开**（菜单栏图标 → 退出）才会生效。
不授权的话，截到的是桌面壁纸而非真实屏幕内容。

### 为什么图标不在 Dock

打包时设置了 `LSUIElement`，程序**不出现在 Dock 和程序坞**，
只在菜单栏（屏幕右上角）留一个图标。想调出控制面板，
点菜单栏图标 → 「立即截图」，或直接用快捷键。

---

## 快速开始

### 找到并启动它

程序位置：**应用程序 → ScreenFloat**

找不到的话，任选一种：

- 按 <kbd>⌘</kbd><kbd>空格</kbd> 打开 Spotlight，输入 `ScreenFloat`
- 访达里按 <kbd>⌘</kbd><kbd>⇧</kbd><kbd>A</kbd> 跳到「应用程序」，再往下滑到 S 开头
- 终端执行 `open -R /Applications/ScreenFloat.app`，会自动在访达中选中它

> **双击没反应时，先去菜单栏看一眼** —— 程序很可能已在运行，
> 只是界面不在 Dock 上。

### 双击没反应？一键诊断

```bash
cd screenfloat
./diagnose.sh
```

会逐项检查文件完整性、运行状态、日志内容和两项 macOS 权限，
最后直接给出结论与修复建议。

日志在 `~/.screenfloat/screenfloat.log`，手动查看：

```bash
cat ~/.screenfloat/screenfloat.log
```

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 双击没反应 | 程序已在运行，界面在菜单栏 | 点菜单栏右上角图标 |
| 双击没反应 + 日志有 Traceback | 程序崩溃 | 看日志末尾报错 |
| 面板有黄色权限提示 | 全局热键未授权 | 见下方「全局快捷键与输入监控」 |
| 截到的是桌面壁纸 | 缺屏幕录制权限 | 见上方「首次使用需要授权」 |
| 日志无「热键命中」 | 全局热键没收到按键 | 检查输入监控权限 |

### 从源码运行（调试用，会显示终端窗口）

```bash
cd screenfloat
.venv/bin/python -m screenfloat
```

### 三种截图方式，按可用性排序

1. **点控制面板上的「开始截图」按钮** ← 最可靠，任何情况下都能用
2. 控制面板聚焦时按<kbd>⌘</kbd><kbd>⇧</kbd><kbd>S</kbd>
3. 任意应用中按 <kbd>⌘</kbd><kbd>⇧</kbd><kbd>S</kbd>（全局热键）

### 首次使用需要授权

macOS 对截图类应用有隐私保护。首次使用请在：

**系统设置 → 隐私与安全性 → 屏幕与系统音频录制** 中勾选 ScreenFloat

授权后**完全退出程序再重新打开**（菜单栏图标 → 退出）才会生效。

若不授权，截到的会是桌面壁纸而非真实屏幕内容。

## 怎么用

| 操作 | 结果 |
| --- | --- |
| <kbd>⌘</kbd><kbd>⇧</kbd><kbd>S</kbd> | 唤起全屏框选，拖拽选区截图 |
| 框选中<kbd>Esc</kbd> | 取消本次截图 |
| 框选中回车 | 确认选区（等同于松开鼠标） |
| **拖动悬浮窗里的图片** | **投送到微信/QQ/邮件等任意窗口** |
| 拖动标题条 | 移动悬浮窗位置 |
| 双击图片 | 复制到剪贴板 |
| <kbd>⧉</kbd> 按钮 | 复制到剪贴板 |
| <kbd>📌</kbd> 按钮 | 钉住，该图不再自动清除 |
| <kbd>✕</kbd> 按钮 | 关闭并立即删除文件 |

标题栏会实时显示**剩余时间**（如 `29:31 后自动清除`），到点自动消失。

## 拖拽投送的细节

拖出时同时提供两种数据，因此对各种接收方都能用：

- `text/uri-list`：指向缓存目录里的真实 PNG 文件，接收方能拿到原图文件
- `application/x-qt-image`：内存图片，应付只接受图片数据、不接受文件的应用

所以拖进微信/QQ 得到的是**原分辨率图片文件**，不是被压缩过的缩略图。

## 菜单栏菜单

- 立即截图
- 自动清除时长：不自动清除 / 10 / 30 / 60 / 120 分钟
- 打开缓存文件夹
- 清空全部截图
- 退出

## 配置

配置文件位于 `~/.screenfloat/config.json`：

```json
{
  "cache_dir": "~/Pictures/ScreenFloatCache",
  "expire_minutes": 30,
  "hotkey": "cmd+shift+s",
  "float_max_width": 320,
  "hide_during_drag": false,
  "start_minimized": true
}
```

| 字段 | 说明 |
| --- | --- |
| `cache_dir` | 缓存目录，截图自动存入这里 |
| `expire_minutes` | 自动清除时长，`0` 表示永不自动清除 |
| `hotkey` | 全局快捷键，格式 `cmd+shift+s` |
| `float_max_width` | 悬浮卡片最大宽度（逻辑像素），大图会等比缩放 |
| `hide_during_drag` | 拖出时是否临时隐藏悬浮窗 |

快捷键改了之后需要重启程序生效。

## 项目结构

```
screenfloat/
├── screenfloat/
│   ├── __main__.py     # 入口
│   ├── app.py          # 装配各模块 + 定时清理 + 单实例锁
│   ├── panel.py        # 控制面板（不依赖热键的截图入口）
│   ├── capture.py      # 全屏抓屏 + 遮罩框选 + Retina 换算
│   ├── store.py        # 缓存落盘、过期判定、自动清理、启动恢复
│   ├── floatwin.py# 悬浮卡片 + 拖出投送 + 标题栏交互
│   ├── hotkey.py       # 全局快捷键（CGEventTap）
│   ├── tray.py         # 菜单栏图标与菜单
│   └── config.py       # 配置读写
├── build_app.sh        # 打包成 .app
├── diagnose.sh        # 一键诊断（双击没反应时用）
└── tests/
    ├── smoke.py          # 缓存与清理逻辑测试
    ├── stale_object_check.py # Qt 对象失效容错测试
    ├── overlay_render_check.py # 截图遮罩绘制测试
    ├── gui_check.py      # GUI 层联调测试
    └── hotkey_check.py   # 热键解析与注册测试
```

## 测试

```bash
.venv/bin/python tests/smoke.py       # 逻辑测试
.venv/bin/python tests/gui_check.py   # GUI 联调
.venv/bin/python tests/hotkey_check.py # 热键
```

## 实现要点

**全局热键为什么用 CGEventTap**

试过两条路，都不通，过程记录在此避免重走：

1. `pyobjc-framework-Carbon`：新版 pyobjc 已移除 Carbon 模块，只剩元数据文件
2. Carbon + ctypes 直调系统框架：能注册成功，但 Carbon 事件需要
   `ReceiveNextEvent` 泵，而 Qt 的 Cocoa 循环已在消费同一队列，
   强行争抢导致 `PostEvent` 返回 -50（eventClassInvalid），回调永不触发，
   期间还发生过一次段错误

最终选 `CGEventTap`：由 Cocoa 主循环直接派发，无需手动泵事件。
它挂在 `kCGSessionEventTap` 上，安装后事件自动流入回调。

**两个必须记下的坑**

- CGEventTap 的回调签名要用**标准库 `ctypes.CFUNCTYPE`**。
  `objc.CFUNCTYPE` 和 `objc.c_void_p` 在 pyobjc 里都不存在，
  用了会抛 AttributeError——这个报错曾被误判成「权限被拒」，
  导致方向跑偏很久
- `CGEventTapCreate` 在权限不足时可能**返回成功但静默收不到事件**，
  所以要配合 `CGPreflightListenEventAccess()` 打印真实权限状态

**Retina 清晰度**
遮罩窗口用逻辑像素，截图像素用设备像素（Retina 下 2 倍）。裁剪时按
`screen.devicePixelRatio()` 换算，并裁剪前先与图片实际边界求交集，避免
多屏或边缘选区越界。

**缓存清理的三条触发路径**
① 60 秒巡检定时器（过期即删）；② 手动关闭卡片；③ 启动时扫描目录，
把过期残留删掉、把仍然新鲜的重新悬浮出来（异常退出后不会丢图）。

**QPainter.fillRect 的重载陷阱（曾导致框选完全看不见）**

`p.fillRect(rect, 0, 0, 0, 255)` 这种「矩形 + rgba 四参数」的写法在
PySide6 里**不存在**，只有 `(x, y, w, h, color)` 和 `(QRect, QColor)` 两种。
写错会每帧抛 TypeError，连带
`QBackingStore::endPaint() called with active painter`，
表现为「框选时看不到任何痕迹」。

所以选区擦亮改用「四周画暗色矩形、留出选区」的方式，
不依赖 `CompositionMode_Clear`——更稳定也不会逐帧闪烁。

**Qt 对象失效的坑（曾导致程序静默崩溃）**

PySide6 的 widget 被销毁后，Python 引用还在，但它已经是空壳——
`is not None` 判断为真，访问任何方法却会抛
`RuntimeError: Internal C++ object already deleted`。

悬浮窗被关闭后，1 秒一次的倒计时定时器仍在刷新它的标题栏，
一抛异常，定时器连带整个进程崩掉，**表现为「双击没反应」**。

正确做法是用 `shiboken6.isValid(w)` 判断对象是否还有效，
并在 `tick_all` / `close_all` / `on_window_closed` 三处都做防护。
`tests/stale_object_check.py` 专门覆盖这个场景。

**单实例锁不能只看文件是否存在**

启动器最初写成「锁文件存在就退出」，结果进程崩溃后锁文件残留，
之后双击永远静默退出、毫无提示。正确做法是把判断交给程序内的
`QLockFile`（它会校验锁对应的进程是否存活），
并设置 `setStaleLockTime(30_000)` 允许清理陈旧锁。

## 已知限制

- 目前仅在 macOS 实测通过。代码结构已预留平台分支，但 Windows/Linux 未验证。
- 全局热键依赖 macOS 权限机制，在部分启动方式下可能失效；
  此时请用控制面板按钮截图（见上文排查章节）。
- 屏幕录制权限：macOS 14+ 首次抓屏需在「系统设置 → 隐私与安全性 → 屏幕录制」
  中授权，否则抓到的会是桌面壁纸。
- 快捷键被其他应用占用时注册会失败，此时程序会弹通知提示，仍可从控制面板手动截图。

## 后续可做

- 多显示器：目前跟随主屏幕，可改为跟随鼠标所在屏幕
- 延时截图（3/5 秒后截，便于截动画）
- 图片标注（画箭头、方框、马赛克）
- 历史截图面板（`⌘⇧H` 唤出）
- 打包为独立 `.app`（py2app）