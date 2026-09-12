# 三角洲口琴自动演奏器（学习项目）

这是一个用 Python 编写的口琴曲谱播放器。当前版本为 v1.0.0，已有可视化桌面界面，可以直接选择曲目、查看信息、导入曲谱或 MIDI、设置热键并控制播放；原有命令行功能仍然保留。

> 默认模式不会发送真实输入。只有使用 `--real-input` 才会向当前前台窗口发送 Windows 键鼠事件。游戏对第三方自动化程序可能有处罚，请在用于游戏前确认当时有效的官方规则并自行评估账号风险。本项目不会读取、修改或注入游戏进程，也不会实现反作弊绕过。

## 当前目标

- 读取文本曲谱。
- 支持普通、降调、半音和升调。
- 根据 BPM（每分钟拍数）计算按键持续时间。
- 导入 `.song` 或 `.txt` 曲谱并加入用户曲库。
- 把单旋律 `.mid` 或 `.midi` 文件转换成 `.song` 曲谱。
- 使用文件名或中文标题选择内置曲目和用户曲目。
- 默认使用 F8 开始、F9 紧急停止、F10 暂停或继续播放，并允许更换功能键。
- 在终端显示当前事件数和播放百分比。
- 默认在终端中安全预览，也可以显式开启 Windows 真实输入。
- 锁定 F8 启动时的前台窗口，切换窗口后自动停止并释放输入。
- 在桌面界面中完成曲目选择、导入、设置和进度查看。

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

## 下载 Windows 版

不想安装 Python 时，可以前往 [GitHub Releases](https://github.com/jackhaumluck-commits/delta-harmonica-player/releases) 下载最新版 `DeltaHarmonicaPlayer.exe`，保存到任意文件夹后双击启动。程序不需要安装，用户曲谱和设置仍会保存在 `%LOCALAPPDATA%\DeltaHarmonicaPlayer` 中。

需要向游戏发送真实输入时，请右键可执行文件并选择“以管理员身份运行”。发布文件目前没有数字签名，因此 Windows 首次打开时可能显示安全提醒；请只从本项目的 GitHub Releases 页面下载，并可用同一页面提供的 `.sha256` 文件核对完整性。

## 运行源码

需要 Python 3.10 或更高版本。首次使用或依赖发生变化时，在项目目录中安装项目：

```powershell
python -m pip install -e .
```

之后可以执行下面的命令。

### 桌面界面（推荐）

启动桌面界面：

```powershell
python -X utf8 -m harmonica_player --gui
```

界面左侧是内置曲目和用户曲目列表，选中后会显示标题、BPM、事件数和时长。可以直接导入 `.song`、`.txt`、`.mid` 或 `.midi` 文件；当 MIDI 有多个音符轨道时，界面会列出轨道名称和音符数，让你选择其中一个。

第一次使用时，可以点击左侧的“导入和使用教程”。教程会说明文本曲谱与 MIDI 的导入方法、安全预演与真实输入的区别，以及默认的 F8、F9、F10 播放快捷键。

默认是不会发送键鼠事件的“安全预演”。在这个模式下可以点击“开始”，也可以使用全局热键。勾选真实输入后，必须先把程序以管理员身份运行，再切换到目标窗口并按开始热键；为了避免误把播放器界面当成目标，真实输入不会由界面里的“开始”按钮直接启动。播放中仍可用全局停止键和暂停键控制。

热键和倒计时会保存在当前 Windows 用户的应用数据目录。真实输入开关不会保存，每次启动都会恢复为关闭。

查看内置曲目和用户曲目：

```powershell
python -X utf8 -m harmonica_player --list-songs
```

按名称预览曲库中的曲目：

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

### 导入自己的曲谱

外部曲谱可以使用 `.song` 或 `.txt` 扩展名，内容必须符合本项目的曲谱格式并使用 UTF-8 编码。导入前程序会先检查格式：

```powershell
python -X utf8 -m harmonica_player --import-song examples/user_song_template.txt
```

上面的命令使用项目附带的导入示例；以后只需将路径换成自己的曲谱文件。

导入成功后，曲谱会以 `.song` 文件保存在当前 Windows 用户的 `%LOCALAPPDATA%\DeltaHarmonicaPlayer\songs` 文件夹中，并可以通过文件名或中文标题选择。首次运行 v1.0 时，程序也会自动复制旧版项目 `songs` 文件夹中的曲谱，且不会覆盖同名文件：

```powershell
python -X utf8 -m harmonica_player --song "我的曲子"
```

用户曲谱默认不会被 Git 提交。文件名或标题与现有曲目冲突时，程序会拒绝导入，避免选择到错误的歌曲。

### 导入 MIDI

v1.0 可以把 MIDI 旋律转换成可编辑的 `.song` 文件并加入用户曲库：

```powershell
python -X utf8 -m harmonica_player --import-midi "D:\Music\melody.mid"
```

如果暂时没有 MIDI 文件，可以先生成项目附带的测试示例：

```powershell
python -X utf8 examples/create_midi_example.py
python -X utf8 -m harmonica_player --import-midi examples/generated_midi_scale.mid
```

转换后的文件会保存在 `songs` 文件夹，可以先打开检查，也可以直接预览：

```powershell
python -X utf8 -m harmonica_player --song generated_midi_scale
```

程序会自动选择唯一的有音符轨道。如果 MIDI 中有多个有音符轨道，错误信息会列出轨道编号；选择其中一个重新导入：

```powershell
python -X utf8 -m harmonica_player --import-midi "D:\Music\multi-track.mid" --midi-track 1
```

默认音高映射以 MIDI 中央 C（编号 60）作为 `1 normal`：低一个八度使用 `down`，高一个八度使用 `up`，中央八度的升半音使用 `semitone`。当所选轨道中出现和弦或重叠音符时，相近起奏的音符会合并成一组并保留每组最高音；下一组开始时会结束上一音，避免钢琴延音遮住后续节奏。对于多声部 MIDI，低于 G3 的选中音会保持音名并上移八度，以减少低声部伴奏对主旋律的干扰；单旋律 MIDI 不使用这项优化。其他无法直接演奏的音符会保持音名，并移动到最近的可演奏八度。为了让游戏稳定识别输入，导入时相邻音符的起奏至少间隔 0.10 秒，过密音符会保留先出现的一个；连续音符之间还会预留约 0.02 秒松键空隙。这些处理不会拉长曲子的整体时间。程序会在生成曲谱和导入结果中说明这些有损转换。当前仍不支持播放中改变 BPM 或延音踏板。

MIDI 解析使用 [Mido](https://mido.readthedocs.io/en/stable/)，项目只需要它的文件读取能力，不需要实时 MIDI 端口后端。

### 计时播放和自定义热键

在 Windows 上启动安全的计时预演：

```powershell
python -X utf8 -m harmonica_player examples/demo.song --timed
```

程序启动后会一直等待：按 `F8` 后倒计时 3 秒并开始预演，按 `F10` 暂停或继续，按 `F9` 可在倒计时、播放或暂停中立即停止；完成或停止后可以再次按 `F8`。播放时会显示当前事件数和完成百分比。按 `Ctrl+C` 退出程序。这个模式只打印动作，不发送真实输入。

可以用 `--countdown` 修改倒计时，例如：

```powershell
python -X utf8 -m harmonica_player examples/demo.song --timed --countdown 5
```

如果 F8、F9 或 F10 已被其他软件占用，程序会报告无法注册全局热键。

开始、停止和暂停键可以分别更换为 F1 到 F24，三个按键不能重复。例如：

```powershell
python -X utf8 -m harmonica_player --song twinkle_twinkle --timed --start-key F5 --stop-key F6 --pause-key F7
```

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

每次向 GitHub 推送 `main` 或创建 PR 时，GitHub Actions 也会在 Python 3.10 和 3.13 上自动运行这些测试。

### 构建 Windows 可执行文件

需要 Python 3.10 或更高版本。安装打包工具并执行构建脚本：

```powershell
python -m pip install ".[build]"
.\scripts\build_windows.ps1
```

生成的文件位于 `dist\DeltaHarmonicaPlayer.exe`，旁边的 `.sha256` 文件用于校验下载是否完整。GitHub 上推送与程序版本一致的标签（例如 `v1.0.0`）时，发布流程会自动测试、打包，并把这两个文件加入 GitHub Release；手动运行该流程只会生成可下载的测试产物。

## v1.0

- 提供可视化曲库、曲谱与 MIDI 导入、热键设置和播放控制。
- 提供 Windows 单文件可执行程序，并通过 GitHub Releases 发布。
- 内置《小星星》、变调练习和《送别》曲谱。

不会加入运行时速度倍率、从指定事件开始或循环播放；BPM 继续作为曲谱本身的节奏信息保留。

