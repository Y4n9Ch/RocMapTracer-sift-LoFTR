import os
import requests
from PIL import Image
from io import BytesIO
import time

# ================= 核心配置区域 =================
# 已经为你替换好了真实的 URL 规律
BASE_URL = "https://wiki-dev-patch-oss.oss-cn-hangzhou.aliyuncs.com/res/lkwg/map-3.0/7/tile-{x}_{y}.png"

# 【安全测试范围】围绕 2040 附近抓取 5x5 的网格
# 等测试成功后，你可以自己去网页边缘抓取真实的极限边界值填进来
X_MIN = -12
X_MAX = 11
Y_MIN = -11
Y_MAX = 11

TILE_SIZE = 256  # 瓦片图标准尺寸


# ================================================

def download_and_stitch():
    # 1. 计算最终画布的宽高
    width = (X_MAX - X_MIN + 1) * TILE_SIZE
    height = (Y_MAX - Y_MIN + 1) * TILE_SIZE

    print(f"👉 准备创建一块 {width} x {height} 像素的画布...")
    result_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # 2. 伪装请求头，防止被服务器识别为爬虫拦截
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://map.17173.com/',
        'Origin': 'https://map.17173.com'
    }

    total_tiles = (X_MAX - X_MIN + 1) * (Y_MAX - Y_MIN + 1)
    current_tile = 0

    # 3. 循环遍历并下载拼图
    for x in range(X_MIN, X_MAX + 1):
        for y in range(Y_MIN, Y_MAX + 1):
            current_tile += 1
            url = BASE_URL.format(x=x, y=y)
            print(f"进度 {current_tile}/{total_tiles} | 正在下载瓦片: X={x}, Y={y} ...")

            try:
                response = session.get(url, headers=headers, timeout=10)

                if response.status_code == 200:
                    # 将下载的二进制数据转为图片对象
                    img_data = BytesIO(response.content)
                    tile = Image.open(img_data).convert("RGBA")

                    # 计算精确的粘贴坐标
                    paste_x = (x - X_MIN) * TILE_SIZE
                    paste_y = (y - Y_MIN) * TILE_SIZE

                    # 贴入画布
                    result_image.paste(tile, (paste_x, paste_y))
                else:
                    # 没画图的虚空边界报 404 是正常的，跳过即可
                    print(f"  [跳过] X={x}, Y={y} 处为空白区域 (状态码: {response.status_code})")

                # 延时 0.1 秒，避免请求过快被服务器拉黑
                time.sleep(0.1)

            except Exception as e:
                print(f"  [错误] 下载 X={x}, Y={y} 失败: {e}")

    # 4. 导出成品
    print("\n✅ 下载与拼接完成！正在保存...")
    save_path = "big_map.png"
    result_image.save(save_path)
    print(f"🎉 大功告成！文件已保存至代码同目录下的: {save_path}")


if __name__ == "__main__":
    # 如果没安装 requests 和 pillow，请在终端执行 pip install requests pillow
    download_and_stitch()