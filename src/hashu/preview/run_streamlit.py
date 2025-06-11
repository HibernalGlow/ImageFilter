"""
pHash 图片相似度分析工具 - Streamlit 启动器
运行此脚本启动 Web 界面
"""
import subprocess
import sys
from pathlib import Path

def install_requirements():
    """安装必需的依赖包"""
    requirements = [
        "streamlit",
        "pillow",
        "pillow-avif",
        "pillow-jxl", 
        "imagehash",
        "pandas",
        "plotly",
        "openpyxl"
    ]
    
    print("正在检查并安装依赖包...")
    for package in requirements:
        try:
            __import__(package)
            print(f"✓ {package} 已安装")
        except ImportError:
            print(f"正在安装 {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def main():
    """启动 Streamlit 应用"""
    # install_requirements()
    
    app_path = Path(__file__).parent / "streamlit_app.py"
    
    print("\n" + "="*50)
    print("🚀 启动 pHash 图片相似度分析工具")
    print("="*50)
    print(f"应用路径: {app_path}")
    print("浏览器将自动打开，如果没有请手动访问显示的URL")
    print("按 Ctrl+C 停止应用")
    print("="*50 + "\n")
    
    # 启动 Streamlit
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", 
        str(app_path),
        "--server.address", "localhost",
        "--server.port", "8505",
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false"
    ])

if __name__ == "__main__":
    main()
