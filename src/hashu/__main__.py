"""
多进程哈希计算优化使用示例
"""
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List

# 导入优化工具
from hashu.utils.hash_process_config import setup_multiprocess_hash_environment
from hashu.core.calculate_hash_custom import ImageHashCalculator, HashCache

from loguru import logger
import os
import sys
from pathlib import Path
from datetime import datetime

def setup_logger(app_name="app", project_root=None, console_output=True):
    """配置 Loguru 日志系统
    
    Args:
        app_name: 应用名称，用于日志目录
        project_root: 项目根目录，默认为当前文件所在目录
        console_output: 是否输出到控制台，默认为True
        
    Returns:
        tuple: (logger, config_info)
            - logger: 配置好的 logger 实例
            - config_info: 包含日志配置信息的字典
    """
    # 获取项目根目录
    if project_root is None:
        project_root = Path(__file__).parent.resolve()
    
    # 清除默认处理器
    logger.remove()
    
    # 有条件地添加控制台处理器（简洁版格式）
    if console_output:
        logger.add(
            sys.stdout,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level.icon} {level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        )
    
    # 使用 datetime 构建日志路径
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
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

logger, config_info = setup_logger(app_name="hashu", console_output=True)

def calculate_hash_worker(image_path: str) -> dict:
    """工作进程函数：计算单个图片的哈希值
    
    Args:
        image_path: 图片路径
        
    Returns:
        dict: 包含路径和哈希结果的字典
    """
    try:
        # 在多进程环境下，使用预加载缓存
        result = ImageHashCalculator.calculate_phash(
            image_path, 
            auto_save=False,  # 多进程下关闭自动保存
            use_preload=True  # 使用预加载缓存
        )
        
        return {
            'path': image_path,
            'result': result,
            'success': True
        }
    except Exception as e:
        return {
            'path': image_path,
            'result': None,
            'success': False,
            'error': str(e)
        }


def batch_calculate_hashes_multiprocess(image_paths: List[str], 
                                       max_workers: int = 4) -> List[dict]:
    """多进程批量计算图片哈希值
    
    Args:
        image_paths: 图片路径列表
        max_workers: 最大工作进程数
        
    Returns:
        List[dict]: 计算结果列表
    """
    logger.info(f"🚀 开始多进程哈希计算，共 {len(image_paths)} 个文件，{max_workers} 个进程")
    
    # 配置多进程环境
    setup_multiprocess_hash_environment(
        enable_auto_save=False,  # 关闭自动保存，避免文件写入冲突
        enable_global_cache=True,  # 启用全局缓存查询
        preload_cache_from_files=True  # 预加载缓存文件
    )
    
    results = []
    start_time = time.time()
    
    try:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_path = {
                executor.submit(calculate_hash_worker, path): path 
                for path in image_paths
            }
            
            # 收集结果
            completed_count = 0
            for future in as_completed(future_to_path):
                try:
                    result = future.result()
                    results.append(result)
                    completed_count += 1
                    
                    if completed_count % 10 == 0:  # 每10个文件输出一次进度
                        logger.info(f"📊 进度: {completed_count}/{len(image_paths)} "
                                  f"({completed_count/len(image_paths)*100:.1f}%)")
                        
                except Exception as e:
                    path = future_to_path[future]
                    logger.error(f"❌ 处理失败 {path}: {e}")
                    results.append({
                        'path': path,
                        'result': None,
                        'success': False,
                        'error': str(e)
                    })
                    
    except Exception as e:
        logger.error(f"❌ 多进程执行失败: {e}")
        return []
    
    end_time = time.time()
    
    # 统计结果
    successful = sum(1 for r in results if r['success'])
    failed = len(results) - successful
    
    logger.info(f"✅ 多进程哈希计算完成!")
    logger.info(f"📊 总耗时: {end_time - start_time:.2f}秒")
    logger.info(f"📊 成功: {successful}, 失败: {failed}")
    logger.info(f"📊 平均速度: {len(image_paths)/(end_time - start_time):.2f} 文件/秒")
    
    return results


def compare_single_vs_multiprocess(image_dir: str, max_workers: int = 4) -> None:
    """比较单进程和多进程的性能差异
    
    Args:
        image_dir: 图片目录
        max_workers: 最大工作进程数
    """
    from hashu.core.calculate_hash_custom import ImgUtils
    
    # 获取图片文件
    image_files = ImgUtils.get_img_files(image_dir)
    if not image_files:
        logger.warning(f"❌ 目录中没有找到图片文件: {image_dir}")
        return
    
    # 限制测试文件数量（避免测试时间过长）
    test_files = image_files[:50] if len(image_files) > 50 else image_files
    logger.info(f"🧪 性能测试开始，使用 {len(test_files)} 个文件")
    
    # 单进程测试
    logger.info("\n=== 单进程测试 ===")
    start_time = time.time()
    single_results = []
    
    for i, img_path in enumerate(test_files):
        try:
            result = ImageHashCalculator.calculate_phash(img_path, auto_save=False)
            single_results.append({'path': img_path, 'result': result, 'success': True})
            
            if (i + 1) % 10 == 0:
                logger.info(f"📊 单进程进度: {i+1}/{len(test_files)}")
                
        except Exception as e:
            single_results.append({'path': img_path, 'result': None, 'success': False, 'error': str(e)})
    
    single_time = time.time() - start_time
    single_success = sum(1 for r in single_results if r['success'])
    
    # 多进程测试
    logger.info("\n=== 多进程测试 ===")
    multi_results = batch_calculate_hashes_multiprocess(test_files, max_workers)
    multi_time = time.time() - start_time - single_time
    multi_success = sum(1 for r in multi_results if r['success'])
    
    # 性能比较
    logger.info("\n=== 性能比较 ===")
    logger.info(f"📊 单进程: {single_time:.2f}秒, 成功: {single_success}/{len(test_files)}")
    logger.info(f"📊 多进程: {multi_time:.2f}秒, 成功: {multi_success}/{len(test_files)}")
    
    if multi_time > 0:
        speedup = single_time / multi_time
        logger.info(f"🚀 加速比: {speedup:.2f}x")
        logger.info(f"📈 效率提升: {(speedup-1)*100:.1f}%")


if __name__ == "__main__":
    # 测试多进程优化功能
    logger.info("🧪 开始测试多进程哈希计算优化功能")
    
    # 配置多进程环境
    logger.info("⚙️ 配置多进程环境...")
    setup_multiprocess_hash_environment(
        enable_auto_save=False,
        enable_global_cache=True, 
        preload_cache_from_files=True
    )
    
    # 显示缓存统计
    stats = HashCache.get_cache_stats()
    logger.info(f"📊 缓存统计: 大小={stats['cache_size']}, 已初始化={stats['initialized']}")
    # logger.info(f"📊 多进程配置: {stats['multiprocess_config']}")
    
    # 尝试查找一些测试图片
    test_dirs = [
        r"E:\2EHV\test",
        r"D:\1VSCODE\Projects\ImageAll\ImageFilter\test_images",
        ".",  # 当前目录
    ]
    
    found_images = []
    for test_dir in test_dirs:
        if Path(test_dir).exists():
            from hashu.core.calculate_hash_custom import ImgUtils
            images = ImgUtils.get_img_files(test_dir)
            if images:
                found_images.extend(images[:5])  # 最多取5个文件
                logger.info(f"✅ 在 {test_dir} 找到 {len(images)} 个图片文件")
                break
    
    if found_images:
        logger.info(f"🚀 开始测试 {len(found_images)} 个图片文件")
        
        # 测试单个文件计算
        test_file = found_images[0]
        logger.info(f"📝 测试单个文件: {test_file}")
        
        result = ImageHashCalculator.calculate_phash(
            test_file, 
            auto_save=False,
            use_preload=True
        )
        
        if result:
            logger.info(f"✅ 哈希计算成功: {result['hash']}")
            logger.info(f"📊 缓存命中: {'是' if result.get('from_cache') else '否'}")
        else:
            logger.error("❌ 哈希计算失败")
        
        # 如果有多个文件，测试批量处理
        if len(found_images) > 1:
            logger.info(f"🔄 测试批量处理 {len(found_images)} 个文件")
            batch_results = batch_calculate_hashes_multiprocess(found_images, max_workers=2)
            
            successful = sum(1 for r in batch_results if r['success'])
            logger.info(f"📊 批量处理结果: 成功 {successful}/{len(found_images)}")
            
    else:
        logger.warning("❌ 没有找到测试图片文件")
        logger.info("💡 可以在以下位置放置测试图片:")
        for test_dir in test_dirs:
            logger.info(f"   - {test_dir}")
        
        # 创建一个示例配置
        logger.info("\n📝 多进程优化使用示例:")
        logger.info("```python")
        logger.info("from hashu.utils.hash_process_config import setup_multiprocess_hash_environment")
        logger.info("from hashu.core.calculate_hash_custom import ImageHashCalculator")
        logger.info("")
        logger.info("# 配置多进程环境")
        logger.info("setup_multiprocess_hash_environment(")
        logger.info("    enable_auto_save=False,  # 多进程下关闭自动保存")
        logger.info("    enable_global_cache=True,  # 启用全局缓存")
        logger.info("    preload_cache_from_files=True  # 预加载缓存")
        logger.info(")")
        logger.info("")
        logger.info("# 计算哈希值")
        logger.info("result = ImageHashCalculator.calculate_phash(")
        logger.info("    'image.jpg',")
        logger.info("    auto_save=False,  # 多进程下关闭自动保存")
        logger.info("    use_preload=True  # 使用预加载缓存")
        logger.info(")")
        logger.info("```")
        
    logger.info("✅ 多进程优化测试完成")
