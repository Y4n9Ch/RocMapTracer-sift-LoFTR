"""
游戏画面透明叠加层窗口
在游戏画面上方绘制2.5D导航箭头，鼠标完全穿透
"""
import tkinter as tk
import math
import ctypes
from ctypes import windll


class OverlayWindow:
    """全屏透明叠加窗口，用于在游戏画面上绘制2.5D导航箭头"""

    def __init__(self, root):
        self.root = root
        self.top = tk.Toplevel(root)
        self.top.title("导航叠加层")

        # 全屏无边框置顶
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)

        # 关键：使用 transparentcolor 实现真透明背景
        self._transparent_color = "#010101"  # 近乎纯黑的特殊颜色作为透明色
        self.top.configure(bg=self._transparent_color)
        self.top.attributes("-transparentcolor", self._transparent_color)

        # 覆盖全屏
        screen_w = self.top.winfo_screenwidth()
        screen_h = self.top.winfo_screenheight()
        self.top.geometry(f"{screen_w}x{screen_h}+0+0")

        # 创建画布
        self.canvas = tk.Canvas(
            self.top,
            bg=self._transparent_color,
            highlightthickness=0,
            width=screen_w,
            height=screen_h
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 启用鼠标穿透
        self.top.update_idletasks()
        self._set_click_through()

        # 状态变量
        self._visible = True
        self._arrow_items = []

    def _set_click_through(self):
        """设置窗口鼠标穿透"""
        try:
            hwnd = windll.user32.GetParent(self.top.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        except Exception as e:
            print(f"⚠️ 设置鼠标穿透失败: {e}")

    def update_arrow(self, screen_x, screen_y, angle_rad, distance, route_name="", rotation_offset=0):
        """
        在屏幕坐标 (screen_x, screen_y) 处绘制2.5D导航箭头

        参数:
            screen_x, screen_y: 箭头起点的屏幕绝对坐标（角色底边中点）
            angle_rad: 箭头方向角度（弧度，0=右，π/2=下）
            distance: 到目标的距离（用于调整箭头长度）
            route_name: 可选的路线名称文字
            rotation_offset: 角度偏移（度），用于校准2.5D游戏视角旋转
        """
        # 清除旧箭头
        for item in self._arrow_items:
            try:
                self.canvas.delete(item)
            except Exception:
                pass
        self._arrow_items.clear()

        if angle_rad is None:
            return

        # 🌟 应用角度偏移校准（度 → 弧度）
        angle_rad = angle_rad + math.radians(rotation_offset)

        # --- 箭头参数 ---
        arrow_length = min(max(distance * 0.3, 50), 150)  # 动态长度
        head_size = 18  # 箭头三角头尺寸
        shaft_width = 5  # 箭杆宽度
        shadow_offset = 4  # 阴影偏移

        # 2.5D 透视效果：Y轴压缩
        y_squeeze = 0.5

        # --- 计算箭头关键点（方向不压缩，保持真实指向） ---
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # 箭头尖端
        tip_x = screen_x + arrow_length * cos_a
        tip_y = screen_y + arrow_length * sin_a

        # 箭杆终点（在尖端后退一点）
        shaft_end_x = screen_x + (arrow_length - head_size * 1.5) * cos_a
        shaft_end_y = screen_y + (arrow_length - head_size * 1.5) * sin_a

        # 箭头头部三角形的两个基点
        perp_cos = math.cos(angle_rad + math.pi / 2)
        perp_sin = math.sin(angle_rad + math.pi / 2)

        base1_x = shaft_end_x + head_size * perp_cos
        base1_y = shaft_end_y + head_size * perp_sin
        base2_x = shaft_end_x - head_size * perp_cos
        base2_y = shaft_end_y - head_size * perp_sin

        # --- 绘制阴影（偏移+更暗） ---
        sx, sy = shadow_offset, shadow_offset + 2  # 阴影略偏下方

        # 阴影箭杆
        shadow_shaft = self.canvas.create_line(
            screen_x + sx, screen_y + sy,
            shaft_end_x + sx, shaft_end_y + sy,
            fill="#000000", width=shaft_width + 2,
            stipple="gray50"
        )
        self._arrow_items.append(shadow_shaft)

        # 阴影箭头
        shadow_head = self.canvas.create_polygon(
            tip_x + sx, tip_y + sy,
            base1_x + sx, base1_y + sy,
            base2_x + sx, base2_y + sy,
            fill="#000000", outline="",
            stipple="gray50"
        )
        self._arrow_items.append(shadow_head)

        # --- 绘制主体箭杆 ---
        main_shaft = self.canvas.create_line(
            screen_x, screen_y,
            shaft_end_x, shaft_end_y,
            fill="#4DA6FF", width=shaft_width,
            capstyle=tk.ROUND
        )
        self._arrow_items.append(main_shaft)

        # --- 绘制主体箭头（三角形） ---
        main_head = self.canvas.create_polygon(
            tip_x, tip_y,
            base1_x, base1_y,
            base2_x, base2_y,
            fill="#4DA6FF", outline="#FFFFFF", width=1
        )
        self._arrow_items.append(main_head)

        # --- 绘制箭头起点的小圆圈（角色脚底标记） ---
        dot_r = 4
        dot = self.canvas.create_oval(
            screen_x - dot_r, screen_y - dot_r,
            screen_x + dot_r, screen_y + dot_r,
            fill="#00FFFF", outline="#FFFFFF", width=1
        )
        self._arrow_items.append(dot)

        # --- 绘制目标名称文字 ---
        if route_name:
            text_x = screen_x + 20
            text_y = screen_y - 15
            # 文字阴影
            text_shadow = self.canvas.create_text(
                text_x + 1, text_y + 1,
                text=route_name, fill="#000000",
                font=("微软雅黑", 11, "bold"), anchor=tk.W
            )
            self._arrow_items.append(text_shadow)
            # 文字主体
            text_main = self.canvas.create_text(
                text_x, text_y,
                text=route_name, fill="#00FFFF",
                font=("微软雅黑", 11, "bold"), anchor=tk.W
            )
            self._arrow_items.append(text_main)

    def clear_arrow(self):
        """清除所有箭头图形"""
        for item in self._arrow_items:
            try:
                self.canvas.delete(item)
            except Exception:
                pass
        self._arrow_items.clear()

    def show(self):
        """显示叠加层"""
        if not self._visible:
            self.top.deiconify()
            self._visible = True

    def hide(self):
        """隐藏叠加层"""
        if self._visible:
            self.top.withdraw()
            self._visible = False

    def destroy(self):
        """销毁叠加层窗口"""
        try:
            self.top.destroy()
        except Exception:
            pass
