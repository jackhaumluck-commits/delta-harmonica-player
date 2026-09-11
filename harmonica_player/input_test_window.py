"""Small desktop window for testing real input outside a game."""

from __future__ import annotations

import sys


def run_input_test_window() -> int:
    if sys.platform != "win32":
        raise RuntimeError("输入测试窗口目前只支持 Windows")

    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("口琴键鼠输入测试窗口")
    root.geometry("720x480")
    root.minsize(560, 360)

    ttk.Label(
        root,
        text="把鼠标留在此窗口内，然后在播放器中按 F8。按 F9 可紧急停止。",
        padding=(16, 14),
    ).pack(fill="x")
    ttk.Label(
        root,
        text="播放中请不要切换窗口；本区域会记录键盘和鼠标的按下/释放。",
        padding=(16, 0, 16, 12),
    ).pack(fill="x")

    log = tk.Text(root, state="disabled", font=("Consolas", 12), padx=12, pady=12)
    log.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def append(message: str) -> None:
        log.configure(state="normal")
        log.insert("end", message + "\n")
        log.see("end")
        log.configure(state="disabled")

    root.bind_all(
        "<KeyPress>",
        lambda event: append(f"键盘按下: {event.keysym}"),
    )
    root.bind_all(
        "<KeyRelease>",
        lambda event: append(f"键盘释放: {event.keysym}"),
    )
    for button, name in ((1, "left"), (2, "middle"), (3, "right")):
        root.bind_all(
            f"<ButtonPress-{button}>",
            lambda _event, button_name=name: append(f"鼠标按下: {button_name}"),
        )
        root.bind_all(
            f"<ButtonRelease-{button}>",
            lambda _event, button_name=name: append(f"鼠标释放: {button_name}"),
        )

    root.after(100, root.focus_force)
    root.mainloop()
    return 0
