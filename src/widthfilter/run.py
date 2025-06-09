#!/usr/bin/env python
"""
图片宽度/高度过滤工具启动脚本
"""

import os
import sys
from pathlib import Path

# 添加当前目录到路径
current_dir = Path(__file__).parent.parent.resolve()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 运行主程序
from widthfilter.cli import run

if __name__ == "__main__":
    run() 