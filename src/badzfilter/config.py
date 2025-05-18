"""
程序全局配置模块
"""
import os
from pathlib import Path

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 历史文件路径
HISTORY_FILE = os.path.join(SCRIPT_DIR, 'archive_check_history.json')

# 默认路径列表
DEFAULT_PATHS = [
    Path(r"D:\3EHV"),
    Path(r"E:\7EHV"),
    # 可以在这里添加更多默认路径
]

# 配置日志面板布局
TEXTUAL_LAYOUT = {
    "status": {
        "ratio": 2,
        "title": "📊 状态信息",
        "style": "lightblue"
    },
    "progress": {
        "ratio": 2,
        "title": "🔄 处理进度",
        "style": "lightcyan"
    },
    "success": {
        "ratio": 3,
        "title": "✅ 成功信息",
        "style": "lightgreen"
    },
    "warning": {
        "ratio": 2,
        "title": "⚠️ 警告信息",
        "style": "lightyellow"
    },
    "error": {
        "ratio": 2,
        "title": "❌ 错误信息",
        "style": "lightred"
    }
}

# 支持的压缩文件扩展名
ARCHIVE_EXTENSIONS = ('.zip', '.rar', '.7z', '.cbz')