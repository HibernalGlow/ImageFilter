"""图片宽度/高度过滤工具主模块"""

import sys
import warnings
from PIL import Image, ImageFile

# 基础设置
warnings.filterwarnings('ignore', category=Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = True

# 导入CLI模块
from widthfilter.cli import run

def main():
    """主入口函数"""
    run()

if __name__ == "__main__":
    main()