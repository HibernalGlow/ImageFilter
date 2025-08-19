"""
hashu模块配置管理器
统一管理SQLite数据库路径、JSON文件路径和其他配置项
"""

import os
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

class ConfigManager:
    """hashu模块配置管理器"""
    
    _instance = None
    _config = None
    _config_file = None
    _lock = threading.RLock()
    
    def __new__(cls):
        """单例模式"""
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        """初始化配置管理器"""
        if self._config is None:
            self._load_config()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        # 相对于当前模块的配置文件路径
        current_dir = Path(__file__).parent
        config_path = current_dir / "config.json"
        
        # 如果配置文件不存在，创建默认配置
        if not config_path.exists():
            self._create_default_config(config_path)
        
        return str(config_path)
    
    def _create_default_config(self, config_path: Path):
        """创建默认配置文件"""
        default_config = {
            "sqlite_databases": [
                os.path.expanduser("~/hashu_database.db"),
                # os.path.expanduser("~/hashu_backup.db")
            ],
            "json_hash_files": [
                os.path.expanduser("~/image_hashes_collection.json"),
                os.path.expanduser("~/image_hashes_global.json")
            ],
            "config_files": {
                "hash_files_list": os.path.expanduser("~/hash_files_list.txt"),
                "cache_timeout": 1800,
                "auto_backup_interval": 3600
            },
            "hash_params": {
                "hash_size": 10,
                "hash_version": 1,
                "default_algorithm": "phash"
            },
            "multiprocess_config": {
                "enable_auto_save": True,
                "enable_global_cache": True,
                "use_sqlite": True,
                "sqlite_priority": True,
                "max_workers": 4
            },
            "backup_config": {
                "enable_backup": True,
                "backup_interval_hours": 24,
                "max_backup_files": 5,
                "backup_directory": os.path.expanduser("~/hashu_backups")
            },
            "migration_config": {
                "auto_migrate_json_to_sqlite": True,
                "preserve_json_files": True,
                "migration_log_file": os.path.expanduser("~/hashu_migration.log")
            }
        }
        
        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入默认配置
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"已创建默认配置文件: {config_path}")
    
    def _load_config(self, config_file: str = None):
        """加载配置文件"""
        with self._lock:
            try:
                if config_file is None:
                    config_file = self._get_default_config_path()
                
                self._config_file = config_file
                
                with open(config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                
                # 展开用户路径
                self._expand_user_paths()
                
                logger.info(f"配置文件已加载: {config_file}")
                
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                # 如果加载失败，使用默认配置
                self._config = self._get_fallback_config()
    
    def _expand_user_paths(self):
        """展开配置中的用户路径（~）"""
        def expand_paths(obj):
            if isinstance(obj, dict):
                return {k: expand_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [expand_paths(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith('~'):
                return os.path.expanduser(obj)
            else:
                return obj
        
        self._config = expand_paths(self._config)
    
    def _get_fallback_config(self) -> Dict[str, Any]:
        """获取后备配置"""
        return {
            "sqlite_databases": [os.path.expanduser("~/hashu_database.db")],
            "json_hash_files": [],
            "config_files": {
                "cache_timeout": 1800
            },
            "hash_params": {
                "hash_size": 10,
                "hash_version": 1
            },
            "multiprocess_config": {
                "enable_auto_save": True,
                "enable_global_cache": True,
                "use_sqlite": True,
                "sqlite_priority": True
            }
        }
    
    def reload_config(self, config_file: str = None):
        """重新加载配置文件"""
        self._load_config(config_file)
    
    def save_config(self, config_file: str = None):
        """保存当前配置到文件"""
        with self._lock:
            try:
                if config_file is None:
                    config_file = self._config_file
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=2, ensure_ascii=False)
                
                logger.info(f"配置已保存到: {config_file}")
                
            except Exception as e:
                logger.error(f"保存配置文件失败: {e}")
    
    # 获取配置项的方法
    def get_sqlite_databases(self) -> List[str]:
        """获取SQLite数据库路径列表"""
        return self._config.get("sqlite_databases", [])
    
    def get_primary_sqlite_database(self) -> str:
        """获取主要的SQLite数据库路径"""
        databases = self.get_sqlite_databases()
        return databases[0] if databases else os.path.expanduser("~/hashu_database.db")
    
    def get_json_hash_files(self) -> List[str]:
        """获取JSON哈希文件路径列表"""
        return self._config.get("json_hash_files", [])
    
    def get_cache_timeout(self) -> int:
        """获取缓存超时时间"""
        return self._config.get("config_files", {}).get("cache_timeout", 1800)
    
    def get_hash_params(self) -> Dict[str, Any]:
        """获取哈希参数"""
        return self._config.get("hash_params", {})
    
    def get_multiprocess_config(self) -> Dict[str, Any]:
        """获取多进程配置"""
        return self._config.get("multiprocess_config", {})
    
    def get_backup_config(self) -> Dict[str, Any]:
        """获取备份配置"""
        return self._config.get("backup_config", {})
    
    def get_migration_config(self) -> Dict[str, Any]:
        """获取迁移配置"""
        return self._config.get("migration_config", {})
    
    # 设置配置项的方法
    def set_sqlite_databases(self, databases: List[str]):
        """设置SQLite数据库路径列表"""
        with self._lock:
            self._config["sqlite_databases"] = databases
    
    def add_sqlite_database(self, database_path: str):
        """添加SQLite数据库路径"""
        with self._lock:
            databases = self.get_sqlite_databases()
            if database_path not in databases:
                databases.append(database_path)
                self._config["sqlite_databases"] = databases
    
    def set_json_hash_files(self, files: List[str]):
        """设置JSON哈希文件路径列表"""
        with self._lock:
            self._config["json_hash_files"] = files
    
    def add_json_hash_file(self, file_path: str):
        """添加JSON哈希文件路径"""
        with self._lock:
            files = self.get_json_hash_files()
            if file_path not in files:
                files.append(file_path)
                self._config["json_hash_files"] = files
    
    def update_multiprocess_config(self, config: Dict[str, Any]):
        """更新多进程配置"""
        with self._lock:
            current_config = self._config.get("multiprocess_config", {})
            current_config.update(config)
            self._config["multiprocess_config"] = current_config
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self._config.copy()
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置（深度合并）"""
        with self._lock:
            def deep_merge(base, override):
                for key, value in override.items():
                    if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                        deep_merge(base[key], value)
                    else:
                        base[key] = value
            
            deep_merge(self._config, config)


# 全局配置管理器实例
_config_manager = None
_config_lock = threading.RLock()

def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    with _config_lock:
        if _config_manager is None:
            _config_manager = ConfigManager()
        return _config_manager

def get_config() -> ConfigManager:
    """获取配置管理器实例（便捷函数）"""
    return get_config_manager()

# 便捷函数
def get_sqlite_databases() -> List[str]:
    """获取SQLite数据库路径列表"""
    return get_config_manager().get_sqlite_databases()

def get_primary_sqlite_database() -> str:
    """获取主要的SQLite数据库路径"""
    return get_config_manager().get_primary_sqlite_database()

def get_json_hash_files() -> List[str]:
    """获取JSON哈希文件路径列表"""
    return get_config_manager().get_json_hash_files()

def get_cache_timeout() -> int:
    """获取缓存超时时间"""
    return get_config_manager().get_cache_timeout()

def get_hash_params() -> Dict[str, Any]:
    """获取哈希参数"""
    return get_config_manager().get_hash_params()

def get_multiprocess_config() -> Dict[str, Any]:
    """获取多进程配置"""
    return get_config_manager().get_multiprocess_config()

# 向后兼容性支持
def get_global_hash_files() -> List[str]:
    """获取全局哈希文件路径（向后兼容）"""
    return get_json_hash_files()

def get_global_hash_file() -> str:
    """获取主要的全局哈希文件路径（向后兼容）"""
    files = get_json_hash_files()
    return files[0] if files else os.path.expanduser("~/image_hashes_collection.json")
