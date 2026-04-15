import json
import glob
import os
import cv2
import math
import numpy as np

class RouteManager:
    def __init__(self, base_folder="routes"):
        self.base_folder = base_folder
        self.categories = ["zhiwu", "diquluxian", "qita"]
        self.route_groups = {cat: [] for cat in self.categories}
        self.visibility = {}
        self._load_all_routes()
        self.colors = [(0, 255, 0), (255, 165, 0), (0, 255, 255), (255, 0, 255), (0, 128, 255)]

    def draw_on(self, canvas, vx1, vy1, view_size, player_x=None, player_y=None):
        color_idx = 0

        # 计算人物在当前裁剪画布 (canvas) 上的局部坐标
        local_player_pt = None
        if player_x is not None and player_y is not None:
            local_player_pt = (int(player_x - vx1), int(player_y - vy1))

        close_threshold = 20  # 🌟 靠近判定距离

        for cat in self.categories:
            for route in self.route_groups[cat]:
                name = route.get("display_name")
                if not self.visibility.get(name, False):
                    continue

                pts = route.get("points", [])
                color = self.colors[color_idx % len(self.colors)]
                color_idx += 1

                # 生成局部坐标
                local_pts = [(int(p["x"] - vx1), int(p["y"] - vy1)) for p in pts]

                # 画线
                for i in range(len(local_pts) - 1):
                    cv2.line(canvas, local_pts[i], local_pts[i + 1], color, 2, cv2.LINE_AA)

                if route.get("loop") and len(local_pts) > 2:
                    cv2.line(canvas, local_pts[-1], local_pts[0], color, 2, cv2.LINE_AA)

                # 🌟 画点：使用 zip 将局部坐标(lp)和原始数据字典(p_dict)绑定循环
                for lp, p_dict in zip(local_pts, pts):
                    if 0 <= lp[0] <= view_size and 0 <= lp[1] <= view_size:
                        pt_radius = 5

                        # 1. 如果这个点已经被踩过，直接标黑
                        if p_dict.get("visited", False):
                            pt_color = (0, 0, 0)
                        else:
                            # 2. 如果没被踩过，判断现在是否靠近
                            pt_color = (0, 0, 255)  # 默认红色
                            if local_player_pt:
                                dist = math.hypot(lp[0] - local_player_pt[0], lp[1] - local_player_pt[1])
                                if dist < close_threshold:
                                    p_dict["visited"] = True  # 🌟 核心：打上永久标记
                                    pt_color = (0, 0, 0)  # 标为黑色

                        # 绘制实心圆
                        cv2.circle(canvas, lp, pt_radius, pt_color, -1)

                # 🔄 自动循环：如果这条路线的所有点都已访问，重置全部
                if pts and all(p.get("visited", False) for p in pts):
                    print(f"🔄 路线 [{name}] 所有点位已走完，自动重置！")
                    for p in pts:
                        p["visited"] = False

    def _load_all_routes(self):
        for cat in self.categories:
            cat_path = os.path.join(self.base_folder, cat)
            if not os.path.exists(cat_path):
                os.makedirs(cat_path)
                continue

            for path in glob.glob(os.path.join(cat_path, "*.json")):
                try:
                    file_name = os.path.basename(path)
                    route_name = os.path.splitext(file_name)[0]

                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        data["display_name"] = route_name

                        self.route_groups[cat].append(data)
                        self.visibility[route_name] = False
                except Exception as e:
                    print(f"加载失败 {path}: {e}")

    def get_next_target(self, player_x, player_y, vx1, vy1, search_radius=500):
        """获取玩家当前位置最近的未访问目标点"""
        min_dist = float('inf')
        best_point = None
        best_route_name = None
        best_local_pt = None

        local_player = (player_x - vx1, player_y - vy1)

        for cat in self.categories:
            for route in self.route_groups[cat]:
                name = route.get("display_name")
                if not self.visibility.get(name, False):
                    continue

                pts = route.get("points", [])
                for p_dict in pts:
                    if p_dict.get("visited", False):
                        continue

                    pt_x = int(p_dict["x"] - vx1)
                    pt_y = int(p_dict["y"] - vy1)
                    dist = math.hypot(pt_x - local_player[0], pt_y - local_player[1])

                    if dist < min_dist and dist < search_radius:
                        min_dist = dist
                        best_point = p_dict
                        best_route_name = name
                        best_local_pt = (pt_x, pt_y)

        return best_local_pt, best_point, best_route_name, min_dist

    def get_sequential_target(self, route_name, start_idx=0):
        """按路线顺序获取从 start_idx 开始的下一个未访问目标点
        
        返回: (point_dict, point_index) 或 (None, -1)
        """
        for cat in self.categories:
            for route in self.route_groups[cat]:
                name = route.get("display_name")
                if name != route_name:
                    continue
                if not self.visibility.get(name, False):
                    return None, -1

                pts = route.get("points", [])
                # 从 start_idx 开始向后查找第一个未访问的点
                for i in range(start_idx, len(pts)):
                    if not pts[i].get("visited", False):
                        return pts[i], i
                # 如果后面都访问过了，从头找
                for i in range(0, start_idx):
                    if not pts[i].get("visited", False):
                        return pts[i], i
                # 🔄 全部访问完毕 → 自动重置并从头开始
                print(f"🔄 路线 [{route_name}] 顺序导航走完一圈，自动重置！")
                for p in pts:
                    p["visited"] = False
                return pts[0], 0  # 重置后返回第一个点
        return None, -1

    def find_clicked_point(self, click_x, click_y, vx1, vy1, threshold=15):
        """根据雷达Canvas上的点击坐标，查找最近的路线点
        
        参数:
            click_x, click_y: Canvas上的点击坐标
            vx1, vy1: 当前视图裁剪的左上角偏移
            threshold: 点击判定距离（像素）
        
        返回: (route_name, point_index, point_dict) 或 (None, -1, None)
        """
        best_dist = float('inf')
        best_route = None
        best_idx = -1
        best_point = None

        for cat in self.categories:
            for route in self.route_groups[cat]:
                name = route.get("display_name")
                if not self.visibility.get(name, False):
                    continue
                pts = route.get("points", [])
                for i, p_dict in enumerate(pts):
                    local_x = int(p_dict["x"] - vx1)
                    local_y = int(p_dict["y"] - vy1)
                    dist = math.hypot(click_x - local_x, click_y - local_y)
                    if dist < threshold and dist < best_dist:
                        best_dist = dist
                        best_route = name
                        best_idx = i
                        best_point = p_dict

        return best_route, best_idx, best_point

    def draw_nav_arrow(self, canvas, player_x, player_y, vx1, vy1, view_size, search_radius=500):
        """在人物脚下绘制2.5D导航箭头，指向最近的未访问目标点"""
        result = self.get_next_target(player_x, player_y, vx1, vy1, search_radius)
        if result is None:
            return

        target_local_pt, target_point, route_name, dist = result
        if target_local_pt is None:
            return

        local_player_pt = (int(player_x - vx1), int(player_y - vy1))

        dx = target_local_pt[0] - local_player_pt[0]
        dy = target_local_pt[1] - local_player_pt[1]
        angle = math.atan2(dy, dx)

        arrow_length = min(max(dist * 0.5, 40), 120)

        arrow_tip_x = local_player_pt[0] + int(arrow_length * math.cos(angle))
        arrow_tip_y = local_player_pt[1] + int(arrow_length * math.sin(angle))

        shadow_offset = 4
        base_x1 = local_player_pt[0] + int(10 * math.cos(angle + np.pi * 0.75))
        base_y1 = local_player_pt[1] + int(10 * math.sin(angle + np.pi * 0.75))
        base_x2 = local_player_pt[0] + int(10 * math.cos(angle - np.pi * 0.75))
        base_y2 = local_player_pt[1] + int(10 * math.sin(angle - np.pi * 0.75))

        shadow_pts = np.array([
            [arrow_tip_x + shadow_offset, arrow_tip_y + shadow_offset],
            [base_x1 + shadow_offset, base_y1 + shadow_offset],
            [base_x2 + shadow_offset, base_y2 + shadow_offset]
        ], dtype=np.int32)

        arrow_pts = np.array([
            [arrow_tip_x, arrow_tip_y],
            [base_x1, base_y1],
            [base_x2, base_y2]
        ], dtype=np.int32)

        cv2.fillPoly(canvas, [shadow_pts], (0, 0, 0))
        cv2.fillPoly(canvas, [arrow_pts], (0, 255, 255))

        shaft_end_x = local_player_pt[0] + int((arrow_length - 15) * math.cos(angle))
        shaft_end_y = local_player_pt[1] + int((arrow_length - 15) * math.sin(angle))
        cv2.line(canvas, local_player_pt, (shaft_end_x, shaft_end_y), (0, 255, 255), 4, cv2.LINE_AA)

        from PIL import Image, ImageDraw, ImageFont
        pil_img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        try:
            font = ImageFont.truetype("msyh.ttc", 16)
        except:
            font = ImageFont.load_default()

        text = route_name if route_name else "NEXT"
        draw.text((local_player_pt[0] + 15, local_player_pt[1] - 20), text, font=font, fill=(0, 255, 255))

        canvas[:, :] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
