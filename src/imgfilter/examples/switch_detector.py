"""
使用配置文件切换检测器的示例
"""
import os
import sys
from pathlib import Path
from loguru import logger

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from imgfilter.detectors.factory import DetectorFactory
from imgfilter.core.filter import ImageFilter


def show_current_detector_sources():
    """显示当前使用的检测器源"""
    print("当前检测器配置:")
    for detector_type, source in DetectorFactory._active_sources.items():
        print(f"  {detector_type}: {source}")
    print()


def main():
    # 显示初始配置
    print("=== 初始配置 ===")
    show_current_detector_sources()
    
    # 创建默认过滤器
    filter1 = ImageFilter()
    print(f"默认灰度图检测器类型: {type(filter1.grayscale_detector).__name__}")
    
    # 从配置文件加载配置
    config_file = os.path.join(project_root, "src", "imgfilter", "config", "detector_config.toml")
    print(f"\n=== 从TOML文件加载配置 ({config_file}) ===")
    
    # 修改TOML配置，将灰度检测器切换为deepghs
    print("修改配置：灰度检测器 -> deepghs")
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace('grayscale = "default"', 'grayscale = "deepghs"')
    
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 加载修改后的配置
    DetectorFactory.configure_from_file(config_file)
    show_current_detector_sources()
    
    # 创建新过滤器
    filter2 = ImageFilter()
    print(f"新配置灰度图检测器类型: {type(filter2.grayscale_detector).__name__}")
    
    # 还原配置
    print("\n=== 还原配置 ===")
    content = content.replace('grayscale = "deepghs"', 'grayscale = "default"')
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("配置已还原")


if __name__ == "__main__":
    main()
