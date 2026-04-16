# 🗺️ Game Map Real-time Tracker — 游戏大地图实时跟点助手

基于Bilibili流光开源项目GMT2.0
主页链接：https://space.bilibili.com/700627654
Github：https://github.com/761696148/Game-Map-Tracker
 本项目采用SIFT + LoFTR 双引擎混合架构  
自动截取屏幕小地图，在高清大地图上实时定位玩家坐标，内置路线导航引擎，支持资源采集路线的自动循环跟点。


---
# 优化

1.基于原版优化启动后不需要手动选择地图，通过sift自动识别坐标后切换AI
2.打开背包、地图、活动页面等操作后，右上角检测小地图失败后不需要重新手动选取坐标
3.切换地图后将由sift自动识别，不需要手动选取
4.优化地图窗口UI，优化锁定逻辑，F9锁定仅锁定窗口
4.添加按住Alt键悬浮地图窗口时鼠标显现

## ✨ 核心特性

### 🧠 双引擎混合追踪

| 引擎 | 作用 | 原理 |
| :--- | :--- | :--- |
| **SIFT** | 全图定位（启动 / 跟丢时） | 传统特征点匹配，快速锁定大致位置 |
| **LoFTR** | 局部精确追踪（正常运行） | Transformer 密集匹配，精度极高 |

系统采用**三态状态机**自动切换：

```
GLOBAL_SCAN（SIFT 全图扫描）
    ↓ 定位成功
LOCAL_TRACK（LoFTR 局部追踪）
    ↓ 连续丢失 ≥5 帧
GLOBAL_SCAN（自动回退重扫）
```

---

## ⚙️ 配置参数说明

所有参数通过 `config.json` 调整，首次运行自动生成：

| 参数 | 默认值 | 说明 |
| :--- | :---: | :--- |
| `AI_REFRESH_RATE` | 200 | 追踪刷新间隔 (ms)，越小越流畅但更吃性能 |
| `AI_CONFIDENCE_THRESHOLD` | 0.6 | LoFTR 匹配置信度阈值，越高越严格 |
| `AI_TRACK_RADIUS` | 500 | 局部追踪搜索半径 (px) |
| `AI_MIN_MATCH_COUNT` | 6 | 最少匹配点数，低于此值视为丢失 |
| `SIFT_MATCH_RATIO` | 0.9 | SIFT Lowe's ratio 阈值 |
| `SIFT_MIN_MATCH_COUNT` | 5 | SIFT 最少匹配点数 |
| `ARROW_HSV_LOW/HIGH` | — | 小地图箭头 HSV 色彩范围 |
| `WINDOW_GEOMETRY` | 400x400 | 悬浮窗初始尺寸与位置 |

---

## 🖥️ 操作指南

### 快捷键

| 按键 | 功能 |
| :---: | :--- |
| `F9` | 切换锁定/解锁模式 |
| `Home` | 打开手动选点窗口 |
| `Alt (按住)` | 锁定模式下临时解除穿透，可操作按钮 |

### UI 操作

- **菜单栏**：勾选路线类别下的具体路线以启用显示
- **透明度滑条**：调节悬浮窗透明度
- **选择点位按钮**：打开大地图手动定位（滚轮缩放 / 左键平移 / 双击确认）
- **双击路线点**：在雷达地图上双击某个路线点，启动从该点开始的顺序导航

---

## 🛠️ 源码运行（面向开发者）

**环境要求**：Python 3.9+，支持 CUDA 的 NVIDIA 显卡（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/你的用户名/Game-Map-Tracker.git
cd Game-Map-Tracker

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 PyTorch GPU 版（关键！pip 默认装 CPU 版）
# 请前往 https://pytorch.org 选择对应 CUDA 版本的安装命令

# 4. 下载大地图
python download_map.py

# 5. 首次运行（会弹出小地图校准器）
python main_ai.py
```

> ⚠️ 首次启动需要校准小地图位置：将绿色圆框对准游戏中的小地图区域，按回车确认。

---

## 📝 路线数据格式

路线文件为 JSON 格式，存放在 `routes/` 对应子目录下：

```json
{
  "display_name": "路线显示名称",
  "loop": true,
  "points": [
    {"x": 1234, "y": 5678},
    {"x": 2345, "y": 6789}
  ]
}
```

- `loop`：是否为环形路线（首尾相连）
- `points`：路线点的大地图像素坐标序列

---


## 注意事项

本项目仅供学习研究使用。