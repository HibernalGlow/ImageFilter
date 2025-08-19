import sys
import signal
from loguru import logger

def safe_exit(signum=None, frame=None):
    logger.info("安全退出，返回码0。")
    sys.exit(0)


def setup_safe_exit():
    signal.signal(signal.SIGINT, safe_exit)
    # 可根据需要添加更多信号处理 