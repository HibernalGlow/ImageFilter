import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

class ConfigManager:
    """配置管理类，处理所有与配置相关的逻辑"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        self.config_path = config_path
        if not self.config_path:
            self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        
        # 加载配置
        self._config = self._load_config()
        
        # 设置默认值
        self.default_min_size = self._config["default_settings"]["min_size"]
        self.default_hamming_distance = self._config["default_settings"]["hamming_distance"]
        self.default_lpips_threshold = self._config["default_settings"]["lpips_threshold"]
        self.textual_layout = self._config["textual_layout"]
        self.blacklist_keywords = self._config.get("archive_settings", {}).get("blacklist_keywords", 
                                   ["merged_", "temp_", "backup_", ".new", ".trash"])
        
        # TUI和日志配置
        self.has_tui = True
        self.logger_config = {}
    
    def _load_config(self) -> Dict[str, Any]:
        """从JSON文件加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            # 返回默认配置
            return {
                "default_settings": {
                    "min_size": 630,
                    "hamming_distance": 12,
                    "lpips_threshold": 0.02
                },
                "archive_settings": {
                    "blacklist_keywords": ["merged_", "temp_", "backup_", ".new", ".trash"]
                },
                "textual_layout": {
                    "cur_stats": {
                        "ratio": 1,
                        "title": "📊 总体进度",
                        "style": "lightyellow"
                    },
                    "cur_progress": {
                        "ratio": 1,
                        "title": "🔄 当前进度",
                        "style": "lightcyan"
                    },
                    "file_ops": {
                        "ratio": 2,
                        "title": "📂 文件操作",
                        "style": "lightpink"
                    },
                    "hash_calc": {
                        "ratio": 2,
                        "title": "🔢 哈希计算",
                        "style": "lightblue"
                    },
                    "update_log": {
                        "ratio": 1,
                        "title": "🔧 系统消息",
                        "style": "lightwhite"
                    }
                },
                "preset_configs": {}
            }
    
    def setup_logger(self, app_name="app", project_root=None, use_tui=True, force_console=False):
        """配置日志系统
        
        Args:
            app_name: 应用名称，用于日志目录
            project_root: 项目根目录，默认为当前文件所在目录
            use_tui: 是否使用TUI界面
            force_console: 是否强制启用控制台输出
            
        Returns:
            Dict: 日志配置信息
        """
        # 更新TUI状态
        self.has_tui = use_tui
        
        # 获取项目根目录
        if project_root is None:
            project_root = Path(__file__).parent.resolve()
        
        # 清除默认处理器
        logger.remove()
        
        # 根据TUI状态和force_console决定是否启用控制台输出
        console_output = force_console or not use_tui
        if console_output:
            logger.add(
                sys.stdout,
                level="INFO",
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
            )
        
        # 使用 datetime 构建日志路径
        from datetime import datetime
        current_time = datetime.now()
        date_str = current_time.strftime("%Y-%m-%d")
        hour_str = current_time.strftime("%H")
        minute_str = current_time.strftime("%M%S")
        
        # 构建日志目录和文件路径
        log_dir = os.path.join(project_root, "logs", app_name, date_str, hour_str)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{minute_str}.log")
        
        # 添加文件处理器
        logger.add(
            log_file,
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
        )
        
        # 保存日志配置
        self.logger_config = {
            'log_file': log_file,
        }
        
        # 记录日志系统初始化信息
        status_message = "TUI界面" if use_tui else "控制台输出"
        logger.info(f"日志系统已初始化，应用名称: {app_name}，使用模式: {status_message}")
        
        return self.logger_config
    
    def get_preset_configs(self) -> Dict[str, Dict[str, Any]]:
        """获取预设配置"""
        return self._config["preset_configs"]
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self._config 