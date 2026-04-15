import cv2
import numpy as np
import mss
import tkinter as tk
from PIL import Image, ImageTk
import torch
import ssl
import config
import os
import sys
import subprocess
import threading
import time
import math
import ctypes
import ctypes.wintypes
from ctypes import windll
from pynput import keyboard


# 🌟 导入自定义模块
from tracker_engine import LoftrEngine
from route_manager import RouteManager
from minimap_arrow import detect_arrow_angle

ssl._create_default_https_context = ssl._create_unverified_context

# 隐藏控制台黑框
if sys.platform == "win32":
    try:
        hw = ctypes.windll.kernel32.GetConsoleWindow()
        if hw:
            ctypes.windll.user32.ShowWindow(hw, 0)
    except Exception:
        pass


def run_selector_if_needed(force=False):
    minimap_cfg = config.settings.get("MINIMAP", {})
    has_valid_config = minimap_cfg and "top" in minimap_cfg and "left" in minimap_cfg

    if not has_valid_config or force:
        print("未检测到有效的小地图坐标，或请求重新校准。")
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
            selector_path = os.path.join(base_dir, "MinimapSetup.exe")
            command = [selector_path]
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            selector_path = os.path.join(base_dir, "selector.py")
            command = [sys.executable, selector_path]
        try:
            subprocess.run(command, check=True)
            import importlib
            importlib.reload(config)
        except Exception:
            sys.exit(1)


# ==========================================
# 🌟 大地图手动选点窗口
# ==========================================
class MapSelectorWindow:
    def __init__(self, root, display_map_bgr, logic_map_shape, callback, close_callback, route_mgr, shared_check_vars):
        self.top = tk.Toplevel(root)
        self.top.title("⚠️ 目标丢失 - 请在大地图上双击定位 (可勾选路线)")
        self.top.attributes("-topmost", True)
        self.top.geometry("1000x800")
        self.top.configure(bg="#2b2b2b")

        self.top.protocol("WM_DELETE_WINDOW", self.on_close)

        self.callback = callback
        self.close_callback = close_callback

        # 🌟 接收主程序的路线管理器和复选框变量，实现状态完全同步
        self.route_mgr = route_mgr
        self.shared_check_vars = shared_check_vars

        self.logic_h, self.logic_w = logic_map_shape
        # 将原始 BGR 图像转换为 RGB 供 Tkinter 显示
        self.full_img_rgb = cv2.cvtColor(display_map_bgr, cv2.COLOR_BGR2RGB)
        self.img_h, self.img_w = self.full_img_rgb.shape[:2]

        # 🌟 独立构建子窗口的顶部菜单和画布
        self.build_ui()

        self.scale = min(1000 / self.img_w, 800 / self.img_h)
        self.offset_x, self.offset_y = 0, 0
        self.start_x, self.start_y = 0, 0

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<MouseWheel>", self.on_scroll)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

        self.top.update()
        self.center_map()
        self.draw_map()

    def build_ui(self):
        # 1. 顶部操作栏
        self.menu_frame = tk.Frame(self.top, bg="#333333")
        self.menu_frame.pack(side=tk.TOP, fill=tk.X)

        tk.Label(self.menu_frame, text="💡 操作：滚轮缩放 | 左键平移 | 双击确认 | 路线:",
                 bg="#333333", fg="yellow", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=10)

        # 2. 路线选择下拉菜单
        display_names = {"zhiwu": "🌿 植物", "diquluxian": "📍 路线", "qita": "📦 其他"}
        for cat in self.route_mgr.categories:
            mb = tk.Menubutton(self.menu_frame, text=f" {display_names[cat]} ▼ ", relief=tk.FLAT,
                               bg="#333333", fg="white", activebackground="#444444", font=("微软雅黑", 9))
            mb.pack(side=tk.LEFT, padx=5)

            menu = tk.Menu(mb, tearoff=0, bg="#2b2b2b", fg="white", selectcolor="#00FF00")
            mb["menu"] = menu

            for route in self.route_mgr.route_groups[cat]:
                r_name = route.get("display_name")
                # 🌟 关键：使用主窗口传来的 tk.BooleanVar，这样两边打钩状态自动双向绑定
                var = self.shared_check_vars[r_name]
                menu.add_checkbutton(label=r_name, variable=var, command=lambda n=r_name: self.toggle_route(n))

        # 3. 图像展示画布
        self.canvas = tk.Canvas(self.top, bg="#1e1e1e", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def on_close(self):
        self.close_callback()
        self.top.destroy()

    def toggle_route(self, name):
        # 更新路线管理器的可见性，并重新画图
        self.route_mgr.visibility[name] = self.shared_check_vars[name].get()
        self.draw_map()

    def center_map(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.offset_x = (cw - self.img_w * self.scale) / 2
        self.offset_y = (ch - self.img_h * self.scale) / 2

    def draw_map(self):
        sw, sh = int(self.img_w * self.scale), int(self.img_h * self.scale)
        if sw <= 0 or sh <= 0: return
        img_resized = cv2.resize(self.full_img_rgb, (sw, sh))

        # 🌟 在缩放后的底图上绘制开启的路线
        color_idx = 0
        for cat in self.route_mgr.categories:
            for route in self.route_mgr.route_groups[cat]:
                name = route.get("display_name")
                if not self.route_mgr.visibility.get(name, False):
                    continue

                pts = route.get("points", [])

                # 获取原颜色 (通常是BGR)，因为当前底图换成了RGB格式，所以需要倒序通道
                bgr_color = self.route_mgr.colors[color_idx % len(self.route_mgr.colors)]
                rgb_color = (bgr_color[2], bgr_color[1], bgr_color[0])
                color_idx += 1

                # 将路线的坐标乘以当前的地图缩放比例
                scaled_pts = [(int(p["x"] * self.scale), int(p["y"] * self.scale)) for p in pts]

                # 连线
                for i in range(len(scaled_pts) - 1):
                    cv2.line(img_resized, scaled_pts[i], scaled_pts[i + 1], rgb_color, 2, cv2.LINE_AA)
                if route.get("loop") and len(scaled_pts) > 2:
                    cv2.line(img_resized, scaled_pts[-1], scaled_pts[0], rgb_color, 2, cv2.LINE_AA)

                # 画点 (保持走过的点为黑色，没走过的为红色)
                for sp, p_dict in zip(scaled_pts, pts):
                    # 注意：这是RGB通道图，红色是 (255, 0, 0)，黑色是 (0, 0, 0)
                    pt_color = (0, 0, 0) if p_dict.get("visited", False) else (255, 0, 0)
                    cv2.circle(img_resized, sp, 4, pt_color, -1)

        self.tk_img = ImageTk.PhotoImage(Image.fromarray(img_resized))
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_img)

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y

    def on_drag(self, event):
        dx, dy = event.x - self.start_x, event.y - self.start_y
        self.offset_x += dx
        self.offset_y += dy
        self.start_x, self.start_y = event.x, event.y
        self.canvas.move("all", dx, dy)

    def on_scroll(self, event):
        f = 1.2 if event.delta > 0 else 0.8
        ns = self.scale * f
        if 0.1 < ns < 10.0:
            mx, my = event.x - self.offset_x, event.y - self.offset_y
            self.offset_x -= mx * (f - 1)
            self.offset_y -= my * (f - 1)
            self.scale = ns
            self.draw_map()

    def on_double_click(self, event):
        ix = (event.x - self.offset_x) / self.scale
        iy = (event.y - self.offset_y) / self.scale
        if 0 <= ix <= self.img_w and 0 <= iy <= self.img_h:
            lx, ly = int(ix / self.img_w * self.logic_w), int(iy / self.img_h * self.logic_h)
            self.top.destroy()
            self.callback(lx, ly)


# ==========================================
# 🌟 主跟点器程序
# ==========================================
class AIMapTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI 雷达 - 鼠标穿透增强版")
        self.root.attributes("-topmost", True)

        # 🌟 设置初始透明度（0.8 表示 80% 不透明）
        self.root.attributes("-alpha", 0.8)

        # 获取初始窗口大小
        self.root.geometry(config.WINDOW_GEOMETRY)
        self.root.update_idletasks()
        
        # 🌟 设置圆角 UI
        if sys.platform == "win32":
            try:
                hwnd = windll.user32.GetParent(self.root.winfo_id())
                # Windows 11 API (DWMWA_WINDOW_CORNER_PREFERENCE)
                windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int))
            except Exception:
                pass

        # --- 1. 基础变量初始化 (必须最先定义) ---
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"使用设备: {self.device}")

        # 加载地图数据
        self.logic_map_bgr = cv2.imread(config.LOGIC_MAP_PATH)
        self.map_height, self.map_width = self.logic_map_bgr.shape[:2]
        self.display_map_bgr = cv2.imread(config.DISPLAY_MAP_PATH)

        # 状态机与追踪变量
        self.state = "GLOBAL_SCAN"  # 初始状态：先用 SIFT 全图定位
        self.last_x, self.last_y = self.map_width // 2, self.map_height // 2
        self.base_search_radius = config.AI_TRACK_RADIUS
        self.current_search_radius = self.base_search_radius
        self.lost_frames, self.max_lost_frames = 0, 4
        self.smoothed_cx, self.smoothed_cy = None, None
        self.selector_open = False
        self._selector_window = None
        self.alt_held = False
        self._cursor_hidden = False
        self.is_running = True
        self.lock = threading.Lock()
        self.latest_display_crop = None

        # 🌟 小地图朝向角度
        self.arrow_angle = None

        # 🌟 顺序导航状态机
        self.nav_active = False          # 导航是否激活（需双击路线点启动）
        self.nav_seq_route = ""          # 当前导航的路线名
        self.nav_seq_idx = 0             # 当前导航的目标点索引

        # 🌟 当前视图偏移（供双击选点使用）
        self.last_vx1 = None
        self.last_vy1 = None

        # 动态视图尺寸变量
        self.view_w = 400
        self.view_h = 400

        # --- 2. 核心模块实例化 ---
        # 2a. AI (LoFTR) 引擎
        self.engine = LoftrEngine(self.device)
        self.route_mgr = RouteManager("routes")

        # 2b. SIFT 全图定位引擎（参考 test/main_sift.py）
        print("🌍 正在初始化 SIFT 全图定位引擎...")
        self.clahe = cv2.createCLAHE(clipLimit=config.SIFT_CLAHE_LIMIT, tileGridSize=(8, 8))
        self.logic_map_gray = cv2.cvtColor(self.logic_map_bgr, cv2.COLOR_BGR2GRAY)
        self.logic_map_gray = self.clahe.apply(self.logic_map_gray)

        self.sift = cv2.SIFT_create()
        print("⚙️ 正在提取大地图 SIFT 特征点（仅运行一次，请稍候）...")
        self.kp_big, self.des_big = self.sift.detectAndCompute(self.logic_map_gray, None)
        print(f"✅ SIFT 大地图特征初始化完成！共找到 {len(self.kp_big)} 个锚点。")

        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)

        # --- 3. UI 构建 ---
        # 顶部菜单栏区域
        self.menu_frame = tk.Frame(self.root, bg="#333333")
        self.menu_frame.pack(side=tk.TOP, fill=tk.X)

        # A. 分类下拉菜单 (基于文件夹)
        display_names = {"zhiwu": "🌿 植物", "diquluxian": "📍 路线", "qita": "📦 其他"}
        self.check_vars = {}
        for cat in self.route_mgr.categories:
            mb = tk.Menubutton(self.menu_frame, text=f" {display_names[cat]} ▼ ", relief=tk.FLAT,
                               bg="#333333", fg="white", activebackground="#444444",
                               activeforeground="#00FF00", font=("微软雅黑", 9))
            mb.pack(side=tk.LEFT, padx=5)

            menu = tk.Menu(mb, tearoff=0, bg="#2b2b2b", fg="white", selectcolor="#00FF00")
            mb["menu"] = menu

            for route in self.route_mgr.route_groups[cat]:
                r_name = route.get("display_name")
                var = tk.BooleanVar(value=False)
                self.check_vars[r_name] = var
                menu.add_checkbutton(label=r_name, variable=var,
                                     command=lambda n=r_name: self.toggle_route(n))

        # B. 透明度调节滑动条
        tk.Label(self.menu_frame, text=" 👁️ 透明度:", bg="#333333", fg="#00FF00", font=("微软雅黑", 9, "bold")).pack(side=tk.LEFT, padx=2)
        self.alpha_scale = tk.Scale(self.menu_frame, from_=0.1, to=1.0, resolution=0.05,
                                    orient=tk.HORIZONTAL, command=self.update_alpha,
                                    bg="#333333", fg="white", highlightthickness=0, bd=0, 
                                    troughcolor="#1e1e1e", relief=tk.FLAT,
                                    sliderlength=15, width=8, length=100, showvalue=False)
        self.alpha_scale.set(0.8)
        self.alpha_scale.pack(side=tk.LEFT, padx=5)

        # C. 🌟 锁定穿透开关 (解决鼠标箭头干扰的关键)
        self.lock_var = tk.BooleanVar(value=False)
        self.lock_cb = tk.Checkbutton(self.menu_frame, text="🔒 锁定", variable=self.lock_var,
                                      command=self.toggle_lock,
                                      bg="#333333", fg="orange", selectcolor="#222222",
                                      activebackground="#444444", font=("微软雅黑", 8))
        self.lock_cb.pack(side=tk.LEFT, padx=10)
        self.start_hotkey_listener()

        # D. Canvas 地图展示区
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.main_frame, bg='#2b2b2b', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.image_on_canvas = None

        # 🌟 双击路线点启动导航
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)

        # E. 选择点位按钮
        tk.Button(self.main_frame, text="选择点位", command=self.trigger_manual_relocate,
                  bg="#4CAF50", fg="white", font=("微软雅黑", 9, "bold"), relief=tk.FLAT).place(x=5, y=5)

        # --- 4. 事件绑定 ---
        self.root.bind("<Configure>", self.on_window_resize)

        # 只有在非锁定状态下才执行悬停变清晰逻辑
        self.root.bind("<Enter>", self._on_mouse_enter)
        self.root.bind("<Leave>", self._on_mouse_leave)

        # --- 5. 启动任务 ---
        self.minimap_region = config.MINIMAP
        self.ai_thread = threading.Thread(target=self.ai_worker_loop, daemon=True)
        self.ai_thread.start()
        self.ui_render_loop()

    def start_hotkey_listener(self):
        """在独立线程中监听全局热键，包括 Alt 按住/松开"""

        def on_press(key):
            # 监听 F9 键
            if key == keyboard.Key.f9:
                new_state = not self.lock_var.get()
                self.lock_var.set(new_state)
                self.root.after(0, self.toggle_lock)
            # 监听 Home 键
            elif key == keyboard.Key.home:
                self.root.after(0, self.trigger_manual_relocate)
            # 监听 Alt 按下：锁定状态下临时允许点击
            elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                if self.lock_var.get() and not self.alt_held:
                    self.alt_held = True
                    self.root.after(0, self._on_alt_press)

        def on_release(key):
            # 监听 Alt 松开：恢复穿透
            if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                if self.lock_var.get() and self.alt_held:
                    self.alt_held = False
                    self.root.after(0, self._on_alt_release)

        # 使用守护线程启动，跟随主程序退出
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()

    def toggle_lock(self):
        """核心：锁定时隐藏边框 + 开启鼠标穿透，按住 Alt 临时解除穿透"""
        is_locked = self.lock_var.get()

        if is_locked:
            self.root.overrideredirect(True)
            self.root.attributes("-alpha", self.alpha_scale.get())
            self.set_click_through(True)  # 锁定后默认鼠标穿透
            self._start_cursor_poll()  # 启动光标检测轮询
            print(">>> [已锁定] 鼠标穿透已开启，经过窗口光标自动隐藏，按住 Alt 可临时操作按钮，按 F9 解锁")
        else:
            self.alt_held = False
            self._restore_cursor()  # 解锁时恢复光标
            self.set_click_through(False)
            self.root.overrideredirect(False)
            self.root.attributes("-alpha", 1.0)
            print(">>> [已解锁] 边框已恢复，窗口可自由操作")

        self.root.update_idletasks()

    def _on_alt_press(self):
        """按住 Alt 时：临时取消穿透，窗口变不透明，恢复光标，允许点击按钮"""
        self._restore_cursor()
        self.set_click_through(False)
        self.root.attributes("-alpha", 1.0)
        print(">>> [Alt 按下] 临时解除穿透，可操作按钮")

    def _on_alt_release(self):
        """松开 Alt 时：恢复穿透和透明度"""
        self.set_click_through(True)
        self.root.attributes("-alpha", self.alpha_scale.get())
        print(">>> [Alt 松开] 恢复穿透模式")

    # --- 光标显示/隐藏管理 ---

    def _start_cursor_poll(self):
        """启动光标位置轮询，检测光标是否在窗口区域内"""
        self._cursor_poll()

    def _cursor_poll(self):
        """定时检测光标位置，在窗口区域内时隐藏光标"""
        if not self.lock_var.get():
            return  # 未锁定时停止轮询

        if not self.alt_held:
            over = self._is_cursor_over_window()
            if over and not self._cursor_hidden:
                windll.user32.ShowCursor(False)
                self._cursor_hidden = True
            elif not over and self._cursor_hidden:
                windll.user32.ShowCursor(True)
                self._cursor_hidden = False

        self.root.after(50, self._cursor_poll)  # 50ms 轮询一次

    def _is_cursor_over_window(self):
        """检测鼠标光标是否在窗口矩形区域内"""
        try:
            pt = ctypes.wintypes.POINT()
            windll.user32.GetCursorPos(ctypes.byref(pt))
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            rect = ctypes.wintypes.RECT()
            windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return rect.left <= pt.x <= rect.right and rect.top <= pt.y <= rect.bottom
        except Exception:
            return False

    def _restore_cursor(self):
        """如果光标被隐藏，恢复显示"""
        if self._cursor_hidden:
            windll.user32.ShowCursor(True)
            self._cursor_hidden = False

    def _on_mouse_enter(self, event):
        if not self.lock_var.get():
            self.root.attributes("-alpha", 1.0)

    def _on_mouse_leave(self, event):
        if not self.lock_var.get():
            self.root.attributes("-alpha", self.alpha_scale.get())

    def set_click_through(self, enabled=True):
        """设置窗口是否允许鼠标穿透"""
        hwnd = windll.user32.GetParent(self.root.winfo_id())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x80000
        WS_EX_TRANSPARENT = 0x20
        style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        if enabled:
            windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        else:
            windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)

    def update_alpha(self, value):
        """同时改变窗口和地图的透明度"""
        self.root.attributes("-alpha", float(value))

    def toggle_route(self, name):
        """更新路线管理器的可见性状态"""
        new_state = self.check_vars[name].get()
        self.route_mgr.visibility[name] = new_state
        print(f"路线 [{name}] 显示状态修改为: {new_state}")

    def trigger_manual_relocate(self):
        if self.state == "MANUAL_RELOCATE" and self.selector_open:
            self._close_selector_window()
            return
        self.selector_open = False
        self.state = "MANUAL_RELOCATE"

    def on_canvas_double_click(self, event):
        """双击雷达Canvas上的路线点，启动顺序导航"""
        # 需要有当前视图偏移量
        if not hasattr(self, 'last_vx1') or self.last_vx1 is None:
            print("⚠️ 还未开始追踪，无法选点")
            return

        # 在路线点中查找被双击的点
        route_name, point_idx, point_dict = self.route_mgr.find_clicked_point(
            event.x, event.y, self.last_vx1, self.last_vy1, threshold=15
        )

        if route_name is not None:
            self.nav_active = True
            self.nav_seq_route = route_name
            self.nav_seq_idx = point_idx
            print(f"🎯 导航已激活！路线: [{route_name}], 起始点: #{point_idx}")
        else:
            print("双击位置附近未找到路线点")

    def _close_selector_window(self):
        """关闭已打开的选点窗口并恢复追踪状态"""
        if hasattr(self, '_selector_window') and self._selector_window is not None:
            try:
                self._selector_window.top.destroy()
            except Exception:
                pass
            self._selector_window = None
        self.selector_open = False
        self.state = "LOCAL_TRACK"

    # 🌟 处理选点窗口关闭时的回调
    def reset_selector_flag(self):
        self.selector_open = False
        # 如果用户关闭了选点窗口，把状态改回本地追踪，防止它死循环反复弹出
        if self.state == "MANUAL_RELOCATE":
            self.state = "LOCAL_TRACK"

    def on_relocate_done(self, x, y):
        print(f"📍 重新定位坐标: X={x}, Y={y}")
        self.last_x, self.last_y = x, y
        self.smoothed_cx, self.smoothed_cy = float(x), float(y)
        self.lost_frames = 0
        self.current_search_radius = self.base_search_radius + 200
        self.state = "LOCAL_TRACK"
        self.selector_open = False

    def on_window_resize(self, event):
        """窗口缩放回调"""
        # 仅响应主窗口尺寸变化，过滤掉子组件变化
        if event.widget == self.root:
            self.view_w = self.canvas.winfo_width()
            self.view_h = self.canvas.winfo_height()


    def ai_worker_loop(self):
        """后台 AI 推理线程 - SIFT 先行定位 + AI 精确追踪混合引擎"""
        with mss.mss() as sct:
            while self.is_running:
                # 1. 拦截：手动定位模式时降低功耗
                if self.state == "MANUAL_RELOCATE":
                    time.sleep(0.1)
                    continue

                start_time = time.time()

                # 2. 获取当前窗口实时尺寸
                current_vw = self.view_w
                current_vh = self.view_h
                half_vw = current_vw // 2
                half_vh = current_vh // 2

                # 3. 截图小地图
                try:
                    screenshot = sct.grab(self.minimap_region)
                    mini_bgr = np.array(screenshot)[:, :, :3]
                except Exception as e:
                    print(f"截图失败: {e}")
                    time.sleep(0.1)
                    continue

                found = False

                # 🌟 检测小地图箭头朝向
                try:
                    detected_angle = detect_arrow_angle(
                        mini_bgr,
                        hsv_low=config.ARROW_HSV_LOW,
                        hsv_high=config.ARROW_HSV_HIGH,
                        min_pixels=config.ARROW_MIN_PIXELS
                    )
                    if detected_angle is not None:
                        self.arrow_angle = detected_angle
                except Exception:
                    pass

                # ==========================================
                # 🌟 状态机核心逻辑
                # ==========================================

                if self.state == "GLOBAL_SCAN":
                    # --- SIFT 全图定位 ---
                    minimap_gray = cv2.cvtColor(mini_bgr, cv2.COLOR_BGR2GRAY)
                    minimap_gray = self.clahe.apply(minimap_gray)
                    mh, mw = minimap_gray.shape

                    kp_mini, des_mini = self.sift.detectAndCompute(minimap_gray, None)

                    if des_mini is not None and len(kp_mini) >= 2:
                        matches = self.flann.knnMatch(des_mini, self.des_big, k=2)

                        good_matches = []
                        for m_n in matches:
                            if len(m_n) == 2:
                                m, n = m_n
                                if m.distance < config.SIFT_MATCH_RATIO * n.distance:
                                    good_matches.append(m)

                        if len(good_matches) >= config.SIFT_MIN_MATCH_COUNT:
                            src_pts = np.float32([kp_mini[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                            dst_pts = np.float32([self.kp_big[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

                            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, config.SIFT_RANSAC_THRESHOLD)

                            if M is not None:
                                center_pt = np.float32([[[mw / 2, mh / 2]]])
                                dst_center = cv2.perspectiveTransform(center_pt, M)
                                temp_x = int(dst_center[0][0][0])
                                temp_y = int(dst_center[0][0][1])

                                if 0 <= temp_x < self.map_width and 0 <= temp_y < self.map_height:
                                    found = True
                                    self.last_x, self.last_y = temp_x, temp_y
                                    self.smoothed_cx, self.smoothed_cy = float(temp_x), float(temp_y)
                                    self.lost_frames = 0
                                    self.current_search_radius = self.base_search_radius
                                    self.state = "LOCAL_TRACK"
                                    print(f"✅ SIFT 全图定位成功！匹配点数={len(good_matches)}, 坐标: X={temp_x}, Y={temp_y} → 切换至 AI 追踪")

                    if not found:
                        print("⛳ SIFT 全图扫描中，尚未匹配成功...")

                elif self.state == "LOCAL_TRACK":
                    # --- AI (LoFTR) 局部精确追踪 ---
                    x1 = max(0, self.last_x - self.current_search_radius)
                    y1 = max(0, self.last_y - self.current_search_radius)
                    x2 = min(self.map_width, self.last_x + self.current_search_radius)
                    y2 = min(self.map_height, self.last_y + self.current_search_radius)

                    local_map = self.logic_map_bgr[y1:y2, x1:x2]

                    if local_map.shape[0] >= 16 and local_map.shape[1] >= 16:
                        t_mini = self.engine.preprocess(mini_bgr)
                        t_local = self.engine.preprocess(local_map)

                        corr = self.engine.match(t_mini, t_local)
                        mk0, mk1 = corr['keypoints0'].cpu().numpy(), corr['keypoints1'].cpu().numpy()
                        conf = corr['confidence'].cpu().numpy()

                        v_idx = conf > config.AI_CONFIDENCE_THRESHOLD
                        mk0, mk1 = mk0[v_idx], mk1[v_idx]

                        if len(mk0) >= config.AI_MIN_MATCH_COUNT:
                            M, _ = cv2.findHomography(mk0, mk1, cv2.RANSAC, config.AI_RANSAC_THRESHOLD)
                            if M is not None:
                                h, w = mini_bgr.shape[:2]
                                center = cv2.perspectiveTransform(np.float32([[[w / 2, h / 2]]]), M)
                                rx, ry = center[0][0][0] + x1, center[0][0][1] + y1

                                if 0 <= rx < self.map_width and 0 <= ry < self.map_height:
                                    if self.smoothed_cx is None:
                                        self.smoothed_cx, self.smoothed_cy = rx, ry
                                    else:
                                        dist = np.sqrt((rx - self.smoothed_cx) ** 2 + (ry - self.smoothed_cy) ** 2)
                                        if dist < 500:
                                            alpha = 0.15 if dist < 15 else 0.45
                                            self.smoothed_cx = alpha * rx + (1 - alpha) * self.smoothed_cx
                                            self.smoothed_cy = alpha * ry + (1 - alpha) * self.smoothed_cy
                                            found = True

                    # 状态维护
                    if found:
                        self.last_x, self.last_y = int(self.smoothed_cx), int(self.smoothed_cy)
                        self.lost_frames, self.current_search_radius = 0, self.base_search_radius
                    else:
                        self.lost_frames += 1
                        if self.lost_frames == 1:
                            self.current_search_radius += 300
                        elif self.lost_frames >= 5:
                            # AI 连续丢失 5 帧，回退给 SIFT 重新全图定位
                            print(f"⚠️ AI 连续丢失 {self.lost_frames} 帧，回退至 SIFT 全图定位...")
                            self.state = "GLOBAL_SCAN"
                            self.lost_frames = 0
                            self.smoothed_cx, self.smoothed_cy = None, None

                # 7. 动态渲染裁剪 (核心修改：使用窗口实时宽高)
                vx1, vy1 = max(0, self.last_x - half_vw), max(0, self.last_y - half_vh)
                vx2, vy2 = min(self.map_width, self.last_x + half_vw), min(self.map_height, self.last_y + half_vh)

                # 🌟 存储当前视图偏移（供双击查找路线点使用）
                self.last_vx1 = vx1
                self.last_vy1 = vy1

                # 裁剪展示用大地图
                crop = self.display_map_bgr[vy1:vy2, vx1:vx2].copy()

                # 8. 绘制路线
                self.route_mgr.draw_on(crop, vx1, vy1, max(current_vw, current_vh), self.last_x, self.last_y)

                # 9. 绘制玩家箭头 (原生小地图箭头抠图)
                mh, mw = mini_bgr.shape[:2]
                asize = 12
                arrow = mini_bgr[mh // 2 - asize: mh // 2 + asize, mw // 2 - asize: mw // 2 + asize].copy()

                ay_local, ax_local = self.last_y - vy1 - asize, self.last_x - vx1 - asize

                if 0 <= ay_local < crop.shape[0] - 2 * asize and 0 <= ax_local < crop.shape[1] - 2 * asize:
                    roi = crop[ay_local: ay_local + 2 * asize, ax_local: ax_local + 2 * asize]
                    crop[ay_local: ay_local + 2 * asize, ax_local: ax_local + 2 * asize] = \
                        cv2.addWeighted(arrow, 0.8, roi, 0.2, 0)

                # 10. 🌟 顺序导航：当导航激活时，追踪当前目标点
                if self.nav_active and self.nav_seq_route:
                    target_point, new_idx = self.route_mgr.get_sequential_target(
                        self.nav_seq_route, self.nav_seq_idx
                    )
                    if target_point is not None:
                        self.nav_seq_idx = new_idx
                        target_lx = int(target_point["x"] - vx1)
                        target_ly = int(target_point["y"] - vy1)

                        # 在目标点画一个高亮标记（绿色大圆环）
                        if (0 <= target_lx < crop.shape[1] and 0 <= target_ly < crop.shape[0]):
                            cv2.circle(crop, (target_lx, target_ly), 12, (0, 255, 0), 2)
                            cv2.circle(crop, (target_lx, target_ly), 4, (0, 255, 0), -1)
                    else:
                        # 防御性分支：理论上不会进入（get_sequential_target 会自动重置）
                        self.nav_seq_idx = 0
                        print(f"🔄 路线 [{self.nav_seq_route}] 已自动重置，继续循环导航")

                # 11. 雷达地图上的导航箭头（指向最近未访问点）
                self.route_mgr.draw_nav_arrow(crop, self.last_x, self.last_y, vx1, vy1, max(current_vw, current_vh))

                # 12. 放入共享变量供主线程 Canvas 渲染
                with self.lock:
                    self.latest_display_crop = crop

                # 频率控制
                st = max(0, (config.AI_REFRESH_RATE / 1000.0) - (time.time() - start_time))
                time.sleep(st)

    def ui_render_loop(self):
        """主线程渲染循环 - 支持动态窗口缩放"""
        # 获取当前画布的实时尺寸
        current_vw = self.view_w
        current_vh = self.view_h

        if self.state == "MANUAL_RELOCATE":
            if not self.selector_open:
                self.selector_open = True
                torch.cuda.empty_cache()
                self._selector_window = MapSelectorWindow(
                    self.root,
                    self.display_map_bgr,
                    (self.map_height, self.map_width),
                    self.on_relocate_done,
                    self.reset_selector_flag,
                    self.route_mgr,  # 🌟 传路线管理器
                    self.check_vars  # 🌟 传多选框状态，实现内外同步
                )

            # 🌟 修改：创建一个匹配当前窗口尺寸的黑色背景提示图
            # 防止视图尺寸为0时报错
            draw_w = max(current_vw, 100)
            draw_h = max(current_vh, 100)

            blank = np.zeros((draw_h, draw_w, 3), np.uint8)

            # 将提示文字居中显示
            text = "Waiting for Relocation..."
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
            text_x = (draw_w - text_size[0]) // 2
            text_y = (draw_h + text_size[1]) // 2

            cv2.putText(blank, text, (text_x, text_y), font, font_scale, (0, 165, 255), thickness)
            self._render_to_canvas(blank)

        else:
            # 正常追踪状态
            with self.lock:
                if self.latest_display_crop is not None:
                    # 直接渲染 AI 线程根据窗口尺寸裁剪好的画面
                    self._render_to_canvas(self.latest_display_crop)

        # 保持约 33 FPS 的刷新率
        self.root.after(30, self.ui_render_loop)

    def _render_to_canvas(self, crop):
        if crop is None or crop.shape[0] == 0 or crop.shape[1] == 0:
            return
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        self.tk_image = ImageTk.PhotoImage(Image.fromarray(rgb))
        if self.image_on_canvas is None:
            self.image_on_canvas = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        else:
            self.canvas.itemconfig(self.image_on_canvas, image=self.tk_image)


if __name__ == "__main__":
    run_selector_if_needed(force=True)
    root = tk.Tk()
    app = AIMapTrackerApp(root)
    root.mainloop()