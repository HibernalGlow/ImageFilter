"""
多进程哈希计算配置和优化工具
"""
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, List
import dotenv
from hashu.log import logger

dotenv.load_dotenv()

# 导入HashCache用于多进程配置
try:
    from hashu.core.calculate_hash_custom import HashCache, MULTIPROCESS_CONFIG
except ImportError:
    # 如果导入失败，创建一个占位符
    class HashCache:
        @classmethod
        def configure_multiprocess(cls, **kwargs):
            pass
        @classmethod
        def preload_cache_for_multiprocess(cls, cache_dict):
            pass
    MULTIPROCESS_CONFIG = {}

class MultiProcessHashOptimizer:
    """多进程哈希计算优化器"""
    
    def __init__(self):
        self._preloaded_cache = None
        self._lock = threading.Lock()
    
    def setup_multiprocess_environment(self, 
                                     enable_auto_save: bool = False,
                                     enable_global_cache: bool = True,
                                     preload_cache_from_files: bool = True) -> None:
        """设置多进程环境
        
        Args:
            enable_auto_save: 是否启用自动保存（多进程下建议关闭）
            enable_global_cache: 是否启用全局缓存查询
            preload_cache_from_files: 是否预加载缓存文件
        """
        with self._lock:
            # 预加载缓存
            preload_cache = None
            if preload_cache_from_files:
                preload_cache = self._load_all_hash_files()
            
            # 配置HashCache
            HashCache.configure_multiprocess(
                enable_auto_save=enable_auto_save,
                enable_global_cache=enable_global_cache,
                preload_cache=preload_cache
            )
            
            logger.info(f"✅ 多进程环境已配置: auto_save={enable_auto_save}, "
                       f"global_cache={enable_global_cache}, "
                       f"preload_cache={'有' if preload_cache else '无'}")
    
    def _load_all_hash_files(self) -> Dict[str, str]:
        """加载所有哈希文件到内存"""
        try:
            from hashu.core.calculate_hash_custom import GLOBAL_HASH_FILES
            import orjson
            
            all_hashes = {}
            loaded_count = 0
            
            for hash_file in GLOBAL_HASH_FILES:
                if not os.path.exists(hash_file):
                    continue
                    
                try:
                    with open(hash_file, 'rb') as f:
                        data = orjson.loads(f.read())
                    
                    # 处理不同格式的哈希文件
                    if "hashes" in data:
                        # 新格式
                        hashes = data["hashes"]
                        for uri, hash_data in hashes.items():
                            if isinstance(hash_data, dict):
                                if hash_str := hash_data.get('hash'):
                                    all_hashes[uri] = hash_str
                            else:
                                all_hashes[uri] = str(hash_data)
                    else:
                        # 旧格式
                        special_keys = {'_hash_params', 'dry_run', 'input_paths'}
                        for k, v in data.items():
                            if k not in special_keys:
                                if isinstance(v, dict):
                                    if hash_str := v.get('hash'):
                                        all_hashes[k] = hash_str
                                else:
                                    all_hashes[k] = str(v)
                    
                    loaded_count += 1
                    
                except Exception as e:
                    logger.warning(f"加载哈希文件失败 {hash_file}: {e}")
                    continue
            
            if all_hashes:
                logger.info(f"✅ 预加载了 {len(all_hashes)} 个哈希值，来源: {loaded_count} 个文件")
                self._preloaded_cache = all_hashes
                return all_hashes
            else:
                logger.warning("❌ 未能预加载任何哈希值")
                return {}
                
        except Exception as e:
            logger.error(f"❌ 预加载哈希文件失败: {e}")
            return {}
    
    def get_preloaded_cache(self) -> Dict[str, str]:
        """获取预加载的缓存"""
        return self._preloaded_cache or {}
    
    def configure_for_single_process(self) -> None:
        """配置单进程环境（恢复默认设置）"""
        HashCache.configure_multiprocess(
            enable_auto_save=True,
            enable_global_cache=True,
            preload_cache=None
        )
        logger.info("✅ 已恢复单进程环境配置")

# 全局优化器实例
multiprocess_optimizer = MultiProcessHashOptimizer()

# 兼容性接口
def setup_multiprocess_hash_environment(**kwargs):
    """设置多进程哈希计算环境的便捷函数"""
    return multiprocess_optimizer.setup_multiprocess_environment(**kwargs)

def get_multiprocess_hash_config():
    """获取当前多进程配置"""
    return MULTIPROCESS_CONFIG.copy()

# 常量配置 - 添加默认值处理
SCRIPTS_DIR = Path(os.getenv("SCRIPTS_DIR", "."))  # 默认为当前目录
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "."))  # 默认为当前目录
HASH_FILES_LIST = os.path.expanduser(r"E:/1BACKUP/ehv/config/hash_files_list.txt")

# 检查关键路径是否存在，如果不存在则使用相对路径
if SCRIPTS_DIR.exists():
    HASH_SCRIPT = "hashpre"
    DEDUP_SCRIPT = "batchfilter"
else:
    # 使用相对于当前项目的路径
    HASH_SCRIPT = None
    DEDUP_SCRIPT = None

if PROJECT_ROOT.exists():
    PYTHON_EXECUTABLE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
else:    # 使用当前Python解释器
    import sys
    PYTHON_EXECUTABLE = Path(sys.executable)

def get_latest_hash_file_path() -> Optional[str]:
    """获取最新的哈希文件路径
    
    Returns:
        Optional[str]: 最新的哈希文件路径，如果没有则返回None
    """
    try:
        if not os.path.exists(HASH_FILES_LIST):
            return None
            
        with open(HASH_FILES_LIST, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if not lines:
            return None
            
        # 获取最后一行并去除空白字符
        latest_path = lines[-1].strip()
        
        # 检查文件是否存在
        if os.path.exists(latest_path):
            return latest_path
        else:
            logger.info(f"❌ 最新的哈希文件不存在: {latest_path}")
            return None
            
    except Exception as e:
        logger.info(f"❌ 获取最新哈希文件路径失败: {e}")
        return None

def process_artist_folder(folder_path: Path, workers: int = 4, force_update: bool = False) -> Optional[str]:
    """处理画师文件夹，生成哈希文件
    
    Args:
        folder_path: 画师文件夹路径
        workers: 线程数
        force_update: 是否强制更新
        
    Returns:
        Optional[str]: 哈希文件路径
    """
    try:
        # 构建命令
        cmd = f' "{HASH_SCRIPT}" --workers {workers} --path "{str(folder_path)}"'
        if force_update:
            cmd += " --force"
            
        logger.info(f"[#process_log]执行哈希预热命令: {cmd}")
        
        # 执行命令
        process = subprocess.run(
            cmd,
            check=False,  # 不要在失败时抛出异常
            shell=True,
            timeout=3600  # 1小时超时
        )
        
        # 根据退出码/返回码处理结果
        if process.returncode == 0:  # 成功完成
            # 获取最新的哈希文件路径
            hash_file = get_latest_hash_file_path()
            if hash_file:
                logger.info(f"[#update_log]✅ 找到哈希文件: {hash_file}")
                return hash_file
            else:
                logger.info("[#process_log]❌ 未能获取最新的哈希文件路径")
                
        elif process.returncode == 1:
            logger.info("[#process_log]❌ 没有找到需要处理的文件")
        elif process.returncode == 2:
            logger.info("[#process_log]❌ 输入路径不存在")
        elif process.returncode == 3:
            logger.info("[#process_log]❌ 处理过程出错")
        else:
            logger.info(f"[#process_log]❌ 未知错误，退出码: {process.returncode}")
            
        return None
            
    except subprocess.TimeoutExpired:
        logger.info("[#process_log]❌ 哈希预处理超时（1小时）")
    except Exception as e:
        logger.info(f"[#process_log]❌ 处理画师文件夹时出错: {str(e)}")
    return None

def process_duplicates(hash_file: str, target_paths: list[str], params: dict = None, worker_count: int = 2):
    """处理重复文件
    
    Args:
        hash_file: 哈希文件路径
        target_paths: 要处理的目标路径列表
        params: 参数字典，包含处理参数
        worker_count: 工作线程数
    """
    try:
        # 构建命令 - 使用batch_img_filter.py替代直接调用img_filter.py
        cmd = f' "{DEDUP_SCRIPT}"'
        cmd += f' --hash_file "{hash_file}"'
        cmd += f' --max_workers {worker_count}'
        cmd += ' --enable_duplicate_filter'
        cmd += ' --duplicate_filter_mode hash'
        # 示例 batchfilter -hash_file "E:\BaiduNetdiskDownload\备份\[カチワリ実験室 (しノ)]\image_hashes.json" -max_workers 16 --enable_duplicate_filter --duplicate_filter_mode hash
        # 添加参数
        if params:
            if params.get('exclude-paths'):
                # 转为--exclude-paths参数
                for path in params['exclude-paths']:
                    cmd += f' --exclude-paths "{path}"'
                
            if params.get('ref_hamming_distance') is not None:
                cmd += f" --ref_hamming_threshold {params['ref_hamming_distance']}"
                
            # if params.get('self_redup', False):
            #     # 适配batch_img_filter.py的自重复检测
            #     cmd += " --self_redup"
            #     if params.get('hamming_distance'):
            #         cmd += f" --hamming_distance {params['hamming_distance']}"
        
        # 添加目标路径
        for path in target_paths:
            cmd += f' "{path}"'
            
        logger.info(f"[#process_log]执行去重复命令: {cmd}")
        
        # 执行命令
        process = subprocess.run(
            cmd,
            check=False,  # 不要在失败时抛出异常
            shell=True,
            timeout=3600  # 1小时超时
        )
        
        # 根据返回码处理结果
        if process.returncode == 0:
            logger.info("[#update_log]✅ 去重复完成")
        else:
            logger.info(f"[#process_log]❌ 去重复失败，返回码: {process.returncode}")
            
    except subprocess.TimeoutExpired:
        logger.info("[#process_log]❌ 去重复处理超时（1小时）")
    except Exception as e:
        logger.info(f"[#process_log]❌ 处理重复文件时出错: {e}")
if __name__ == '__main__':
    print(PROJECT_ROOT,PYTHON_EXECUTABLE)