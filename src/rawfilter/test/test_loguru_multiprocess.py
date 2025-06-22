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
    print("测试1：loguru提前add（全局）")
    test_loguru_before_main()
    print("测试2：loguru只在主进程和子进程各自add")
    test_loguru_after_main()
    print("请检查 loguru_before_main.log 和 loguru_after_main.log 的文件数量和内容")