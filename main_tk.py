# -*- coding: utf-8 -*-
"""goToWork - tkinter 原生桌面悬浮窗（ctypes系统托盘）"""
import os
import sys
import json
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import messagebox
from datetime import datetime

def resource_path(rel):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

def config_path():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'config.json')

CONFIG_FILE = config_path()
ACCENT = "#3b82f6"

DEFAULT_CONFIG = {
    "salary_month": 8000,
    "work_days_month": 22,
    "work_start_hour": 9.0,
    "work_end_hour": 18.5,
    "lunch_start_hour": 12.0,
    "lunch_end_hour": 13.0,
    "pay_day": 15,
    "on_top": True,
    "locked": False,
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except Exception:
        return None

def save_config(cfg):
    data = {**DEFAULT_CONFIG, **cfg}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


# ---------- ctypes 系统托盘 ----------
WM_TRAYICON = 0x400 + 1
WM_DESTROY = 0x0002
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_ICON = 2
NIF_MESSAGE = 1
NIF_TIP = 4
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
TPM_BOTTOMALIGN = 0x0020
TPM_LEFTBUTTON = 0
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
MF_SEPARATOR = 0x0800

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                            wintypes.WPARAM, wintypes.LPARAM)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]

class TrayIcon:
    """在独立线程中运行的系统托盘"""
    def __init__(self, on_left_click, on_settings, on_quit):
        self.on_left_click = on_left_click
        self.on_settings = on_settings
        self.on_quit = on_quit
        self.on_right_click = lambda x, y: None
        self.hwnd = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32
        hInstance = kernel32.GetModuleHandleW(None)

        # 回调函数引用必须保持
        self._wndproc = WNDPROC(self._wnd_proc)

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hInstance
        wc.lpszClassName = "WorkExeTray"
        wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
        user32.RegisterClassW(ctypes.byref(wc))

        self.hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "Tray", 0, 0, 0, 0, 0,
            None, None, hInstance, None)

        # 使用 Tk 默认应用图标，避免额外 GDI 资源初始化失败。
        hIcon = self._create_icon(user32)

        # 添加托盘图标
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = hIcon
        nid.szTip = "goToWork"
        # Shell_NotifyIconW 属于 shell32.dll，不是 user32.dll。
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            return

        # 消息循环
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _create_icon(self, user32):
        user32.LoadIconW.restype = wintypes.HICON
        return user32.LoadIconW(None, 32512)

    def _wnd_proc(self, hwnd, msg, wParam, lParam):
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        if msg == WM_TRAYICON:
            try:
                if lParam == WM_LBUTTONUP:
                    self.on_left_click()
                elif lParam == WM_RBUTTONUP:
                    self._show_menu(user32)
            except Exception:
                pass
            return 0
        if msg == WM_DESTROY:
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wParam, lParam)

    def _show_menu(self, user32):
        # 由 Tk 绘制菜单，确保中文在不同 Windows 缩放和主题下可见。
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        self.on_right_click(pt.x, pt.y)


class App:
    def __init__(self):
        self.config = load_config() or DEFAULT_CONFIG
        self._drag = None
        self._on_top = self.config.get('on_top', True)
        self._locked = self.config.get('locked', False)
        self._tray = None
        self._tray_menu = None

        self.root = tk.Tk()
        self.root.title("goToWork")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind_all("<ButtonPress-1>", self._drag_start, add="+")
        self.root.bind_all("<B1-Motion>", self._drag_move, add="+")
        self.root.bind_all("<ButtonRelease-1>", self._drag_end, add="+")

        if self.config is None or not os.path.exists(CONFIG_FILE):
            self._show_settings(first_run=True)
        else:
            self._build_main()
            self._start_tray()

    # ---------- 设置页 ----------
    def _show_settings(self, first_run=False):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.overrideredirect(False)
        self.root.geometry("360x420")
        self.root.resizable(False, False)
        self.root.title("goToWork - 设置")

        frm = tk.Frame(self.root)
        frm.pack(fill='both', expand=True, padx=10, pady=10)
        tk.Label(frm, text="goToWork", font=("Microsoft YaHei", 14, "bold")).pack(anchor='w', pady=(0, 4))
        tk.Label(frm, text="先填写薪资信息", fg="#9ca3af", font=("Microsoft YaHei", 9)).pack(anchor='w', pady=(0, 12))

        vmap = {}
        for label, key in [
            ("月薪（元）", "salary_month"),
            ("月工作天数", "work_days_month"),
            ("上班时间（点）", "work_start_hour"),
            ("午休开始（点）", "lunch_start_hour"),
            ("午休结束（点）", "lunch_end_hour"),
            ("下班时间（点）", "work_end_hour"),
            ("每月发薪日（号）", "pay_day"),
        ]:
            row = tk.Frame(frm); row.pack(fill='x', padx=20, pady=6)
            tk.Label(row, text=label, width=16, anchor='w', font=("Microsoft YaHei", 10)).pack(side='left')
            v = tk.StringVar(value=str(self.config.get(key, "")))
            tk.Entry(row, textvariable=v, width=14, font=("Microsoft YaHei", 10)).pack(side='right')
            vmap[key] = v

        def save():
            try:
                self.config = save_config({
                    'salary_month': float(vmap['salary_month'].get()),
                    'work_days_month': int(float(vmap['work_days_month'].get())),
                    'work_start_hour': float(vmap['work_start_hour'].get()),
                    'work_end_hour': float(vmap['work_end_hour'].get()),
                    'lunch_start_hour': float(vmap['lunch_start_hour'].get()),
                    'lunch_end_hour': float(vmap['lunch_end_hour'].get()),
                    'pay_day': int(float(vmap['pay_day'].get())),
                })
                if not (0 <= self.config['work_start_hour'] < self.config['lunch_start_hour']
                        < self.config['lunch_end_hour'] < self.config['work_end_hour'] < 24):
                    raise ValueError
                self._build_main()
                self._start_tray()
            except ValueError:
                messagebox.showerror("错误", "请填写有效数字", parent=self.root)

        tk.Button(frm, text="保存并开始打工", command=save,
                  bg="#111827", fg="white", relief='flat', height=2,
                  font=("Microsoft YaHei", 10, "bold")).pack(fill='x', padx=20, pady=(16, 0))

    # ---------- 主悬浮窗 ----------
    def _build_main(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.overrideredirect(True)
        self.root.geometry("300x420+100+100")
        self.root.update_idletasks()
        try:
            self.root.attributes("-topmost", self._on_top)
        except Exception:
            pass

        outer = tk.Frame(self.root, bg="#f0f2f5")
        outer.pack(fill='both', expand=True)
        self.card = tk.Frame(outer, bg="#ffffff")
        self.card.pack(fill='both', expand=True, padx=3, pady=3)

        content = tk.Frame(self.card, bg="white")
        content.pack(fill='both', expand=True, padx=18, pady=(16, 16))

        # 关闭按钮（默认隐藏，鼠标移入显示）
        self.btn_close = tk.Button(self.card, text="×", bg="white", fg="#9ca3af",
                                   bd=0, font=("Microsoft YaHei", 12, "bold"),
                                   activebackground="white", activeforeground="#111827",
                                   cursor="hand2", command=self.on_close)
        self.btn_close.place(relx=1.0, x=-6, y=4, anchor='ne')
        self.btn_close.place_forget()  # 默认隐藏

        # 鼠标移入移出
        self.card.bind("<Enter>", self._on_enter)
        self.card.bind("<Leave>", self._on_leave)

        # 内容
        tk.Label(content, text="距离下班", bg="white", fg="#9ca3af",
                 font=("Microsoft YaHei", 9)).pack(anchor='w')
        self.lbl_countdown = tk.Label(content, text="00:00:00", bg="white",
                                      fg="#111827", font=("Consolas", 22, "bold"))
        self.lbl_countdown.pack(anchor='w', pady=(2, 10))

        tk.Label(content, text="今日已赚", bg="white", fg="#9ca3af",
                 font=("Microsoft YaHei", 9)).pack(anchor='w')
        self.lbl_earned = tk.Label(content, text="¥ 0.00", bg="white",
                                   fg=ACCENT, font=("Consolas", 24, "bold"))
        self.lbl_earned.pack(anchor='w')
        self.lbl_rate = tk.Label(content, text="赚钱速度：0.0000 元/秒",
                                 bg="white", fg="#9ca3af", font=("Microsoft YaHei", 8))
        self.lbl_rate.pack(anchor='w', pady=(2, 12))

        # 渐变进度条
        self.progress_canvas = tk.Canvas(content, bg="white", height=6, highlightthickness=0)
        self.progress_canvas.pack(fill='x')
        self._pct = 0.0

        self.lbl_progress = tk.Label(content, text="有效工作 0.00 / 0.00 小时",
                                     bg="white", fg="#9ca3af", font=("Microsoft YaHei", 8))
        self.lbl_progress.pack(anchor='w', pady=(4, 10))

        s = {"bg": "white", "fg": "#4b5563", "font": ("Microsoft YaHei", 9)}
        self.lbl_month = tk.Label(content, text="本月累计  ¥ 0.00", **s)
        self.lbl_month.pack(fill='x', pady=1)
        self.lbl_payday = tk.Label(content, text="距发薪日  还有 0 天", **s)
        self.lbl_payday.pack(fill='x', pady=1)
        self.lbl_hour = tk.Label(content, text="时薪  ¥ 0.00", **s)
        self.lbl_hour.pack(fill='x', pady=1)
        self.lbl_daypay = tk.Label(content, text="今日满勤  ¥ 0.00", **s)
        self.lbl_daypay.pack(fill='x', pady=1)
        self.lbl_tip = tk.Label(content, text="加油打工人！", bg="white", fg="#9ca3af",
                                font=("Microsoft YaHei", 8, "italic"), anchor='w')
        self.lbl_tip.pack(fill='x', pady=(10, 0))

        self.refresh()
        self._tick()

    def _bind_drag(self, widget):
        widget.bind("<Button-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)

    def _on_enter(self, e):
        self.btn_close.place(relx=1.0, x=-6, y=4, anchor='ne')

    def _on_leave(self, e):
        # 鼠标不在按钮上时才隐藏
        if not self.btn_close.winfo_containing(e.x_root, e.y_root):
            self.btn_close.place_forget()

    def _drag_start(self, e):
        if self._locked or e.widget.winfo_toplevel() is not self.root:
            self._drag = None
            return
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        if self._drag is None or self._locked or e.widget.winfo_toplevel() is not self.root:
            return
        self.root.geometry("+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1]))

    def _drag_end(self, e):
        self._drag = None

    def on_close(self):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="取消窗口置顶" if self._on_top else "窗口置顶",
                         command=self._toggle_top)
        menu.add_command(label="允许拖动窗口" if self._locked else "锁定窗口位置",
                         command=self._toggle_lock)
        menu.add_separator()
        menu.add_command(label="设置", command=self._show_settings)
        menu.add_command(label="最小化", command=self._minimize)
        menu.add_separator()
        menu.add_command(label="退出", command=self._quit)
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def _toggle_top(self):
        self._on_top = not self._on_top
        try:
            self.root.attributes("-topmost", self._on_top)
        except Exception:
            pass
        self.config['on_top'] = self._on_top
        save_config(self.config)

    def _toggle_lock(self):
        self._locked = not self._locked
        self._drag = None
        self.config['locked'] = self._locked
        save_config(self.config)

    def _minimize(self):
        self.root.withdraw()

    def _start_tray(self):
        if self._tray:
            return
        self._tray = TrayIcon(
            on_left_click=lambda: self.root.after(0, self._toggle_visible),
            on_settings=lambda: self.root.after(0, self._on_tray_settings),
            on_quit=lambda: self.root.after(0, self._quit),
        )
        self._tray.on_right_click = lambda x, y: self.root.after(
            0, lambda: self._show_tray_menu(x, y))
        self._tray.start()

    def _show_tray_menu(self, x, y):
        if self._tray_menu is None:
            self._tray_menu = tk.Menu(self.root, tearoff=0, font=("Microsoft YaHei UI", 9))
        self._tray_menu.delete(0, "end")
        self._tray_menu.add_command(
            label="窗口置顶" if not self._on_top else "取消窗口置顶",
            command=self._toggle_top)
        self._tray_menu.add_command(
            label="锁定窗口位置" if not self._locked else "允许拖动窗口",
            command=self._toggle_lock)
        self._tray_menu.add_separator()
        self._tray_menu.add_command(
            label="显示窗口" if not self.root.winfo_viewable() else "隐藏窗口",
            command=self._toggle_visible)
        self._tray_menu.add_command(label="设置", command=self._on_tray_settings)
        self._tray_menu.add_command(label="最小化", command=self._minimize)
        self._tray_menu.add_separator()
        self._tray_menu.add_command(label="退出", command=self._quit)
        try:
            self._tray_menu.tk_popup(x, y)
        finally:
            self._tray_menu.grab_release()

    def _toggle_visible(self):
        # 在tkinter线程中执行
        self.root.after(0, lambda: (
            self.root.deiconify() if not self.root.winfo_viewable()
            else self.root.withdraw()
        ))

    def _on_tray_settings(self):
        self.root.after(0, self._show_settings)

    def _quit(self):
        self.root.destroy()
        os._exit(0)

    def _tick(self):
        self.refresh()
        self.root.after(800, self._tick)

    def _draw_gradient(self):
        c = self.progress_canvas
        c.delete("all")
        c.update_idletasks()
        w = c.winfo_width() or 260
        h = 6
        c.create_rectangle(0, 0, w, h, fill="#e5e7eb", outline="")
        fw = int(w * self._pct)
        if fw > 0:
            for i in range(fw):
                ratio = i / max(1, fw - 1)
                r = int(0x3b + (0x8b - 0x3b) * ratio)
                g = int(0x82 + (0x5c - 0x82) * ratio)
                b = int(0xf6 + (0xf6 - 0xf6) * ratio)
                c.create_rectangle(i, 0, i + 1, h, fill="#%02x%02x%02x" % (r, g, b), outline="")

    def refresh(self):
        c = self.config
        now = datetime.now()
        sh, eh = c['work_start_hour'], c['work_end_hour']
        def at_hour(hour):
            return now.replace(hour=int(hour), minute=int((hour % 1) * 60),
                               second=0, microsecond=0)

        start, lunch_start = at_hour(sh), at_hour(c['lunch_start_hour'])
        lunch_end, end = at_hour(c['lunch_end_hour']), at_hour(eh)
        effective_seconds = (lunch_start - start).total_seconds() + (end - lunch_end).total_seconds()
        effective_seconds = max(1, effective_seconds)
        worked = max(0, (min(now, lunch_start) - start).total_seconds()) if now > start else 0
        if now > lunch_end:
            worked += max(0, (min(now, end) - lunch_end).total_seconds())
        worked = min(worked, effective_seconds)
        remain = max(0, (end - now).total_seconds())

        work_hours_day = effective_seconds / 3600
        hw = c['salary_month'] / (c['work_days_month'] * work_hours_day)
        sw = hw / 3600
        df = c['salary_month'] / c['work_days_month']
        earned = worked * sw

        if remain > 0:
            h, m, s = int(remain // 3600), int((remain % 3600) // 60), int(remain % 60)
            self.lbl_countdown.config(text="%02d:%02d:%02d" % (h, m, s))
        else:
            self.lbl_countdown.config(text="已下班！")
        self.lbl_earned.config(text="¥ %.2f" % earned)
        self.lbl_rate.config(text="赚钱速度：%.4f 元/秒" % sw)
        self._pct = min(1.0, worked / effective_seconds)
        self._draw_gradient()
        self.lbl_progress.config(text="有效工作 %.2f / %.2f 小时" % (worked/3600, work_hours_day))
        self.lbl_month.config(text="本月累计  ¥ %.2f" % (max(0, now.day - 1) * df))
        pm = now.month if now.day < c['pay_day'] else now.month + 1
        py = now.year
        if pm > 12: pm, py = 1, py + 1
        try:
            pl = max(0, (now.replace(year=py, month=pm, day=c['pay_day']) - now).days)
        except ValueError:
            pl = 0
        self.lbl_payday.config(text="距发薪日（%d号）  还有 %d 天" % (c['pay_day'], pl))
        self.lbl_hour.config(text="时薪  ¥ %.2f" % hw)
        self.lbl_daypay.config(text="今日满勤  ¥ %.2f" % df)
        if earned < 10:
            tip = "刚起步，小钱慢慢攒起来✨"
        elif earned < 30:
            tip = "不错，一顿简餐到手啦！"
        elif earned < 60:
            tip = "很棒，双人奶茶套餐拿下～"
        elif earned < 120:
            tip = "可以好好吃一顿丰盛正餐了！"
        elif earned < 250:
            tip = "厉害，差不多是一张电影票+聚餐预算！"
        elif earned < 500:
            tip = "给力，赚到一件平价衣服啦！"
        elif earned < 1000:
            tip = "很强，差不多是一双不错的球鞋！"
        else:
            tip = "收入可观，继续加油打工人！💪"

        self.lbl_tip.config(text=tip)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = App()
    app.run()
