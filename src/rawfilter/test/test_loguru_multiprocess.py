import os
import sys
from multiprocessing import Process
from loguru import logger
import time

def worker(idx, log_path):
    logger.add(log_path, enqueue=True)
    for i in range(3):
        logger.info(f"[worker {idx}] log {i}")
        time.sleep(0.2)

def worker2(idx, log_path):
    logger.add(log_path, enqueue=True)
    for i in range(3):
        logger.info(f"[worker {idx}] log {i}")
        time.sleep(0.2)

def test_loguru_before_main():
    log_path = "loguru_before_main.log"
    logger.add(log_path, enqueue=True)
    ps = [Process(target=worker, args=(i, log_path)) for i in range(3)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    logger.info("[main] done (before main)")

def test_loguru_after_main():
    log_path = "loguru_after_main.log"
    ps = [Process(target=worker2, args=(i, log_path)) for i in range(3)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    logger.add(log_path, enqueue=True)
    logger.info("[main] done (after main)")

if __name__ == "__main__":
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
        
        # 添加文件处理器（多进程安全，enqueue=True）
        logger.add(
            log_file,
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
            enqueue=True,  # 多进程安全合并日志
    )
        
        # 创建配置信息字典
        config_info = {
            'log_file': log_file,
        }
        
        logger.info(f"日志系统已初始化，应用名称: {app_name}")
        return logger, config_info
    
    logger, config_info = setup_logger(app_name="app_name", console_output=True)
    
    print("测试1：loguru提前add（全局）")
    test_loguru_before_main()
    print("测试2：loguru只在主进程和子进程各自add")
    test_loguru_after_main()
    print("请检查 loguru_before_main.log 和 loguru_after_main.log 的文件数量和内容")