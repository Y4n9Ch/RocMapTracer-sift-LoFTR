"""
小地图箭头朝向检测模块
从小地图截图中提取玩家箭头的方向角度
"""
import cv2
import numpy as np
import math


def detect_arrow_angle(mini_bgr, hsv_low=None, hsv_high=None, min_pixels=30):
    """
    从小地图 BGR 图像中检测箭头指针的朝向角度。

    参数:
        mini_bgr: 小地图截图 (BGR numpy 数组)
        hsv_low:  箭头颜色 HSV 下界, 默认 [0, 0, 200]（白色/亮色箭头）
        hsv_high: 箭头颜色 HSV 上界, 默认 [180, 50, 255]
        min_pixels: 最少像素数，低于此阈值视为检测失败

    返回:
        角度（弧度，0=右，π/2=下，遵循 atan2 约定），或 None 表示检测失败
    """
    if hsv_low is None:
        hsv_low = [0, 0, 200]
    if hsv_high is None:
        hsv_high = [180, 50, 255]

    h, w = mini_bgr.shape[:2]

    # 1. 只关注小地图中心区域的箭头（中心 40% 范围）
    margin_x = int(w * 0.3)
    margin_y = int(h * 0.3)
    center_roi = mini_bgr[margin_y:h - margin_y, margin_x:w - margin_x]

    # 2. 转 HSV 色彩空间，提取箭头颜色区域
    hsv = cv2.cvtColor(center_roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(hsv_low), np.array(hsv_high))

    # 3. 形态学清理噪点
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    # 4. 获取箭头像素坐标
    points = np.column_stack(np.where(mask > 0))  # (row, col) 格式
    if len(points) < min_pixels:
        return None

    # 5. PCA 计算主轴方向
    mean, eigenvectors = cv2.PCACompute(points.astype(np.float32), mean=None)
    center = mean[0]  # 质心 (row, col)
    principal_axis = eigenvectors[0]  # 第一主成分方向 (row, col)

    # 6. 判断箭头尖端方向
    # 将点投影到主轴上，找到最远的两端
    projections = np.dot(points - center, principal_axis)
    idx_max = np.argmax(projections)
    idx_min = np.argmin(projections)

    tip_candidate_1 = points[idx_max]  # 一端
    tip_candidate_2 = points[idx_min]  # 另一端

    # 箭头尖端较窄（附近像素少），尾部较宽（附近像素多）
    # 统计两端附近的像素密度来判断
    radius = max(3, int(len(points) ** 0.3))
    density_1 = np.sum(np.linalg.norm(points - tip_candidate_1, axis=1) < radius)
    density_2 = np.sum(np.linalg.norm(points - tip_candidate_2, axis=1) < radius)

    # 像素密度低的是尖端
    if density_1 <= density_2:
        tip = tip_candidate_1
    else:
        tip = tip_candidate_2

    # 7. 计算从质心到尖端的方向角
    # 注意 points 是 (row, col) = (y, x)，需要转换为 (dx, dy)
    dx = tip[1] - center[1]  # col 方向 = x
    dy = tip[0] - center[0]  # row 方向 = y
    angle = math.atan2(dy, dx)

    return angle
