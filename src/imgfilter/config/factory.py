"""
检测器工厂模块，用于动态切换不同实现的检测器
"""
import os
import toml
import importlib
from pathlib import Path
from typing import Dict, Any, Type, Optional, Callable


class DetectorFactory:
    """检测器工厂类，负责创建和管理不同实现的检测器"""
    
    # 检测器类型枚举
    GRAYSCALE = "grayscale"
    TEXT = "text"
    DUPLICATE = "duplicate"
    SMALL = "small"
    WATERMARK = "watermark"
    
    # 检测器来源枚举
    SOURCE_DEFAULT = "default"
    SOURCE_DEEPGHS = "deepghs"
    
    # 检测器导入映射表，格式为: {detector_type: {source: import_path}}
    _detector_import_map = {
        GRAYSCALE: {
            SOURCE_DEFAULT: "imgfilter.detectors.gray.grayscale:GrayscaleImageDetector",
            SOURCE_DEEPGHS: "imgfilter.deepghs.detectors.grayscale:GrayscaleImageDetector"
        },
        TEXT: {
            SOURCE_DEFAULT: "imgfilter.detectors.text:CVTextImageDetector"
        },
        DUPLICATE: {
            SOURCE_DEFAULT: "imgfilter.detectors.duplicate:DuplicateImageDetector"
        },
        SMALL: {
            SOURCE_DEFAULT: "imgfilter.detectors.small:SmallImageDetector"
        },
        WATERMARK: {
            SOURCE_DEFAULT: "imgfilter.detectors.watermark:WatermarkDetector"
        }
    }
    
    # 当前活跃的检测器源配置
    _active_sources = {
        GRAYSCALE: SOURCE_DEFAULT,
        TEXT: SOURCE_DEFAULT,
        DUPLICATE: SOURCE_DEFAULT,
        SMALL: SOURCE_DEFAULT,
        WATERMARK: SOURCE_DEFAULT
    }
    
    # 检测器类缓存，避免重复导入
    _detector_class_cache = {
        GRAYSCALE: {
            SOURCE_DEFAULT: GrayscaleImageDetector
        },
        SMALL: {
            SOURCE_DEFAULT: SmallImageDetector
        },
        WATERMARK: {
            SOURCE_DEFAULT: WatermarkDetector
        }
    }
    
    # 当前活跃的检测器源配置
    _active_sources = {
        GRAYSCALE: SOURCE_DEFAULT,
        TEXT: SOURCE_DEFAULT,
        DUPLICATE: SOURCE_DEFAULT,
        SMALL: SOURCE_DEFAULT,
        WATERMARK: SOURCE_DEFAULT
    }
    
    @classmethod
    def configure_detector_source(cls, detector_type: str, source: str) -> None:
        """
        配置特定检测器类型使用的源
        
        Args:
            detector_type: 检测器类型
            source: 检测器源
        """
        if detector_type not in cls._detector_map:
            raise ValueError(f"未知的检测器类型: {detector_type}")
            
        if source not in cls._detector_map[detector_type]:
            available_sources = list(cls._detector_map[detector_type].keys())
            raise ValueError(f"检测器 {detector_type} 不支持源 {source}。可用的源: {available_sources}")
            
        cls._active_sources[detector_type] = source
        
    @classmethod
    def configure_from_env(cls) -> None:
        """从环境变量配置检测器源"""
        for detector_type in cls._detector_map:
            env_var = f"IMGFILTER_{detector_type.upper()}_SOURCE"
            source = os.environ.get(env_var)
            if source and source in cls._detector_map[detector_type]:
                cls._active_sources[detector_type] = source
                
    @classmethod
    def configure_from_dict(cls, config: Dict[str, str]) -> None:
        """
        从字典配置检测器源
        
        Args:
            config: 配置字典，格式为 {detector_type: source}
        """
        for detector_type, source in config.items():
            if detector_type in cls._detector_map and source in cls._detector_map[detector_type]:
                cls._active_sources[detector_type] = source
    
    @classmethod
    def configure_from_file(cls, file_path: str, section: str = "detectors") -> None:
        """
        从配置文件加载检测器配置
        
        Args:
            file_path: 配置文件路径
            section: TOML文件中的配置部分，默认为"detectors"(仅TOML文件有效)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"配置文件不存在: {file_path}")
            
        file_ext = Path(file_path).suffix.lower()
        
        try:
            if file_ext == ".json":
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # JSON可能有嵌套结构，尝试获取section
                if section in config:
                    config = config[section]
            elif file_ext in (".toml", ".tml"):
                config = toml.load(file_path)
                # TOML默认就是分段的，获取特定段
                if section in config:
                    config = config[section]
            else:
                raise ValueError(f"不支持的配置文件格式: {file_ext}")
                
            cls.configure_from_dict(config)
        except Exception as e:
            raise RuntimeError(f"加载配置文件失败: {str(e)}")
    
    @classmethod
    def get_detector_class(cls, detector_type: str) -> Type:
        """
        获取检测器类
        
        Args:
            detector_type: 检测器类型
            
        Returns:
            检测器类
        """
        if detector_type not in cls._detector_map:
            raise ValueError(f"未知的检测器类型: {detector_type}")
            
        source = cls._active_sources[detector_type]
        return cls._detector_map[detector_type][source]
    
    @classmethod
    def create_detector(cls, detector_type: str, **kwargs) -> Any:
        """
        创建检测器实例
        
        Args:
            detector_type: 检测器类型
            **kwargs: 传递给检测器构造函数的参数
            
        Returns:
            检测器实例
        """
        detector_class = cls.get_detector_class(detector_type)
        return detector_class(**kwargs)
