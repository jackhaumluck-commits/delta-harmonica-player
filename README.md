# 三角洲口琴自动演奏器（学习项目）

这是一个用 Python 编写的口琴曲谱播放器。当前版本是 v0.4.0，可以读取简单的数字曲谱，计算每个音符需要使用的键盘按键、鼠标修饰键和持续时间，并支持曲目选择、静态预览和按 BPM 计时的终端预演。

> 当前版本不会向游戏发送按键，也不会修改、读取或注入游戏进程。游戏对第三方自动化程序可能有处罚，请在添加真实输入功能前确认官方规则并自行评估账号风险。本项目不会实现反作弊绕过。

## 当前目标

- 读取文本曲谱。
- 支持普通、降调、半音和升调。
- 根据 BPM（每分钟拍数）计算按键持续时间。
- 使用 F8 开始、F9 紧急停止、F10 暂停或继续计时预演。
- 在终端中安全预览演奏动作，不发送真实输入。

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

第一条有效指令必须设置速度：

```text
bpm 120
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

也可以继续直接提供曲谱路径：

```powershell
python -X utf8 -m harmonica_player examples/demo.song
```

在 Windows 上启动计时预演：

```powershell
python -X utf8 -m harmonica_player examples/demo.song --timed
```

程序启动后会一直等待：按 `F8` 后倒计时 3 秒并开始预演，按 `F10` 暂停或继续，按 `F9` 可在倒计时、播放或暂停中立即停止；完成或停止后可以再次按 `F8`。按 `Ctrl+C` 退出程序。

可以用 `--countdown` 修改倒计时，例如：

```powershell
python -X utf8 -m harmonica_player examples/demo.song --timed --countdown 5
```

如果 F8、F9 或 F10 已被其他软件占用，程序会报告无法注册全局热键。当前计时模式只输出“开始”和“释放”等文字，**不会按下真实键盘或鼠标，也不会向游戏发送输入**。

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

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## 计划

1. 加入包含降调、半音和升调的练习曲。
2. 根据更多真实曲谱的体验调整曲谱格式。
3. 保持计时控制与输出模块可替换，为真实输入模块做准备。
4. 打包成方便运行的 Windows 程序。
