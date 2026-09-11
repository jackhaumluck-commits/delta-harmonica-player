# 三角洲口琴自动演奏器（学习项目）

这是一个用 Python 编写的口琴曲谱播放器。当前版本是 v0.6.0，可以读取带中文标题的数字曲谱，计算每个音符需要使用的键盘按键、鼠标修饰键和持续时间，并支持曲目选择、终端预览以及显式开启的 Windows 键鼠输出。

> 默认模式不会发送真实输入。只有使用 `--real-input` 才会向当前前台窗口发送 Windows 键鼠事件。游戏对第三方自动化程序可能有处罚，请在用于游戏前确认当时有效的官方规则并自行评估账号风险。本项目不会读取、修改或注入游戏进程，也不会实现反作弊绕过。

## 当前目标

- 读取文本曲谱。
- 支持普通、降调、半音和升调。
- 根据 BPM（每分钟拍数）计算按键持续时间。
- 使用文件名或中文标题选择内置曲目。
- 使用 F8 开始、F9 紧急停止、F10 暂停或继续播放。
- 默认在终端中安全预览，也可以显式开启 Windows 真实输入。
- 锁定 F8 启动时的前台窗口，切换窗口后自动停止并释放输入。

## 键位规则

| 曲谱音符 | 游戏显示 | 键盘按键 |
| --- | --- | --- |
| `1`–`7` | `1`–`7` | `Z X C V B N M` |
| `8` | 高音 `1` | `,` |

| 曲谱修饰词 | 鼠标动作 |
| --- | --- |
| `normal` | 不按鼠标 |
| `down` | 按住鼠标左键（降调） |
| `semitone` | 按住鼠标中键（半音） |
| `up` | 按住鼠标右键（升调） |
| `rest` | 休止，不发出音符 |

## 曲谱格式

第一条有效指令必须设置速度。可以紧接着添加一行标题，标题要写在第一个音符之前：

```text
bpm 120
title 我的曲子
```

之后每行依次填写“音符、拍数、修饰词”。`0` 代表休止：

```text
1 1 normal
2 0.5 normal
5 1 down
3 0.5 semitone
8 2 up
0 1 rest
```

以 `#` 开头的内容是注释。拍数可以是整数或小数，但必须大于零。

## 运行

需要 Python 3.10 或更高版本。在项目目录中执行：

查看内置曲目：

```powershell
python -X utf8 -m harmonica_player --list-songs
```

按名称预览内置曲目：

```powershell
python -X utf8 -m harmonica_player --song twinkle_twinkle
```

也可以使用带引号的中文标题：

```powershell
python -X utf8 -m harmonica_player --song "小星星（第一段）"
```

也可以继续直接提供曲谱路径：

```powershell
python -X utf8 -m harmonica_player examples/demo.song
```

在 Windows 上启动安全的计时预演：

```powershell
python -X utf8 -m harmonica_player examples/demo.song --timed
```

程序启动后会一直等待：按 `F8` 后倒计时 3 秒并开始预演，按 `F10` 暂停或继续，按 `F9` 可在倒计时、播放或暂停中立即停止；完成或停止后可以再次按 `F8`。按 `Ctrl+C` 退出程序。这个模式只打印动作，不发送真实输入。

可以用 `--countdown` 修改倒计时，例如：

```powershell
python -X utf8 -m harmonica_player examples/demo.song --timed --countdown 5
```

如果 F8、F9 或 F10 已被其他软件占用，程序会报告无法注册全局热键。

### 在测试窗口验证真实输入

第一次使用真实输入时，请先在游戏外测试。打开第一个 PowerShell，进入项目目录并运行：

```powershell
python -X utf8 -m harmonica_player --input-test-window
```

保持测试窗口打开，再打开第二个 PowerShell并运行：

```powershell
python -X utf8 -m harmonica_player --song modifier_exercise --timed --real-input
```

真实输入模式需要管理员权限。请右键 PowerShell 或 Windows Terminal，选择
“以管理员身份运行”，再执行上面的命令；如果权限不足，程序会在等待 F8 前
直接给出操作提示。普通预览和测试窗口本身不要求管理员权限。

把鼠标移到测试窗口内，单击窗口使其位于最前方，然后按 `F8`。程序会锁定这个窗口，倒计时后发送键鼠输入。测试窗口应依次记录普通、左键降调、中键半音和右键升调事件。

- 鼠标修饰键会先按下，键盘音符随后按下。
- 音符结束时会先释放键盘，再释放鼠标。
- 按 `F10` 会立即释放当前输入；继续时重新按下并演奏剩余时长。
- 按 `F9`、按 `Ctrl+C`、发生异常或切换前台窗口都会释放全部输入。

真实输入使用 Windows `SendInput`。如果目标程序的权限级别高于播放器，Windows 可能会阻止输入；真实输入模式因此会预先检查管理员权限，但普通预览仍应使用普通权限运行。

底层实现参考微软官方文档：[SendInput](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput)、[INPUT](https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-input) 和 [GetForegroundWindow](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-getforegroundwindow)。

### 第一首练习曲

v0.3 加入了《小星星》第一段，共 14 个音符，在 BPM 80 下约 12 秒。先查看静态预览：

```powershell
python -X utf8 -m harmonica_player --song twinkle_twinkle
```

再启动计时预演：

```powershell
python -X utf8 -m harmonica_player --song twinkle_twinkle --timed
```

这首曲子只使用普通音符，目的是先判断音高、节奏和现有曲谱格式是否正确。后续曲谱会继续验证鼠标变调。

### 变调按键练习

v0.5 加入了“变调按键练习”，会在低、中、高三个音区依次预演普通、降调、半音和升调：

```powershell
python -X utf8 -m harmonica_player --song modifier_exercise
```

这是一段按键练习，不是一首完整旋律；它用来确认三种鼠标修饰动作与持续时间是否符合预期。

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## 计划

1. 在游戏外测试窗口完成 Windows 键鼠输出验收。
2. 根据更多真实曲谱的体验调整曲谱格式。
3. 增加速度调整、片段循环和自定义热键。
4. 制作桌面界面，并打包成方便运行的 Windows 程序。
