import os
import sys
from pathlib import Path
from datetime import datetime
import traceback
import ctypes
from ctypes import windll, c_wchar_p, c_ulong


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
        enqueue=True,     )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

logger, config_info = setup_logger(app_name="check_cuda_onnx", console_output=True)




# Windows API 错误码获取和信息提取
def get_last_error_message():
    """获取 Windows 最后一次错误的详细信息"""
    error_code = windll.kernel32.GetLastError()
    buf_size = 256
    error_msg = ctypes.create_unicode_buffer(buf_size)
    windll.kernel32.FormatMessageW(
        0x00001000,  # FORMAT_MESSAGE_FROM_SYSTEM
        None,
        error_code,
        0,
        error_msg,
        buf_size,
        None
    )
    return f"错误码: {error_code}, 信息: {error_msg.value.strip()}"

def check_dll_dependencies(dll_path):
    """使用 Windows API 检查 DLL 的依赖项"""
    logger.info(f"正在分析 {dll_path} 的依赖项...")
    if not os.path.exists(dll_path):
        logger.error(f"DLL文件不存在: {dll_path}")
        return
    
    try:
        # 使用 LoadLibraryEx 获取模块句柄
        h_module = windll.kernel32.LoadLibraryExW(c_wchar_p(dll_path), None, 0x00000008)  # DONT_RESOLVE_DLL_REFERENCES
        if h_module == 0:
            logger.error(f"无法加载 DLL 进行依赖分析: {get_last_error_message()}")
            return
        
        # 分析更多依赖信息（通常需要第三方工具或更复杂的代码）
        logger.info(f"成功加载 DLL 进行依赖分析")
        windll.kernel32.FreeLibrary(h_module)
    except Exception as e:
        logger.error(f"分析 DLL 依赖时出错: {e}")
        logger.error(traceback.format_exc())

def check_dll_in_paths(dll_name, search_paths=None):
    """检查指定 DLL 在给定路径列表中是否存在"""
    if search_paths is None:
        # 获取系统 PATH 环境变量
        search_paths = os.environ.get('PATH', '').split(';')
        # 添加可能的 CUDA 路径
        cuda_path = os.environ.get('CUDA_PATH')
        if cuda_path:
            search_paths.append(os.path.join(cuda_path, 'bin'))
    
    logger.info(f"正在搜索 {dll_name} 文件...")
    found_paths = []
    for path in search_paths:
        if not path:
            continue
        full_path = os.path.join(path, dll_name)
        if os.path.exists(full_path):
            found_paths.append(full_path)
            logger.info(f"找到 {dll_name} 在: {full_path}")
    
    if not found_paths:
        logger.error(f"在搜索路径中未找到 {dll_name}")
    return found_paths

def try_load_dll_with_dependencies(dll_name, search_paths=None):
    """尝试加载 DLL 并详细记录加载过程"""
    try:
        logger.info(f"尝试加载 {dll_name}...")
        
        # 1. 如果有指定路径，优先尝试
        if search_paths:
            for path in search_paths:
                full_path = os.path.join(path, dll_name)
                if os.path.exists(full_path):
                    try:
                        logger.info(f"正在加载指定路径的DLL: {full_path}")
                        dll = ctypes.cdll.LoadLibrary(full_path)
                        logger.success(f"成功加载 {dll_name} 从: {full_path}")
                        return dll
                    except Exception as e:
                        logger.error(f"从指定路径加载 {dll_name} 失败: {e}")
                        logger.error(traceback.format_exc())
                        # 尝试获取 Windows 系统错误信息
                        logger.error(f"Windows系统错误: {get_last_error_message()}")
        
        # 2. 尝试直接加载（系统会搜索 PATH）
        try:
            logger.info(f"正在尝试通过系统PATH加载 {dll_name}...")
            dll = ctypes.cdll.LoadLibrary(dll_name)
            logger.success(f"成功通过系统PATH加载 {dll_name}")
            return dll
        except Exception as e:
            logger.error(f"通过系统PATH加载 {dll_name} 失败: {e}")
            logger.error(traceback.format_exc())
            logger.error(f"Windows系统错误: {get_last_error_message()}")
        
        # 3. 搜索可能的路径
        found_paths = check_dll_in_paths(dll_name)
        if found_paths:
            for full_path in found_paths:
                try:
                    logger.info(f"正在尝试加载搜索到的DLL: {full_path}")
                    dll = ctypes.cdll.LoadLibrary(full_path)
                    logger.success(f"成功加载 {dll_name} 从: {full_path}")
                    return dll
                except Exception as e:
                    logger.error(f"从搜索路径加载 {dll_name} 失败: {e}")
                    logger.error(traceback.format_exc())
                    logger.error(f"Windows系统错误: {get_last_error_message()}")
        
        # 4. 检查 DLL 的依赖项
        if found_paths:
            for full_path in found_paths:
                check_dll_dependencies(full_path)
        
        raise FileNotFoundError(f"无法加载 {dll_name}，已尝试所有可能的方法")
        
    except Exception as e:
        logger.error(f"加载 {dll_name} 失败: {e}")
        logger.error(traceback.format_exc())
        return None

# 初始化日志系统
logger, config_info = setup_logger(app_name="cuda_check", console_output=True)

logger.info("=== CUDA/cuDNN/ONNXRuntime GPU 检测 ===")

# 检查CUDA环境变量
cuda_path = os.environ.get('CUDA_PATH')
logger.info(f"CUDA_PATH: {cuda_path}")

# 检查PATH中是否包含CUDA和cuDNN
path = os.environ.get('PATH', '')
logger.info("PATH中包含以下CUDA/cuDNN相关路径:")
for p in path.split(';'):
    if p and ('cuda' in p.lower() or 'cudnn' in p.lower()):
        logger.info(f"  {p}")
        # 检查该目录是否存在
        if not os.path.exists(p):
            logger.warning(f"  路径不存在: {p}")

# 检查CUDA驱动
try:
    logger.info("正在检查 PyTorch CUDA 支持...")
    import torch
    logger.info(f"PyTorch 版本: {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    device_count = torch.cuda.device_count()
    logger.info(f"PyTorch 检测: CUDA 可用: {cuda_available}  设备数: {device_count}")
    if cuda_available:
        device_name = torch.cuda.get_device_name(0)
        logger.info(f"当前设备: {device_name}")
        # 检查 CUDA 版本
        logger.info(f"CUDA 版本: {torch.version.cuda}")
except ImportError as e:
    logger.warning(f"未安装 torch，跳过 PyTorch 检测: {e}")
except Exception as e:
    logger.error(f"PyTorch CUDA 检测失败: {e}")
    logger.error(traceback.format_exc())

# 检查onnxruntime GPU
try:
    logger.info("正在检查 ONNXRuntime GPU 支持...")
    import onnxruntime as ort
    logger.info(f"ONNXRuntime 版本: {ort.__version__}")
    providers = ort.get_available_providers()
    logger.info(f"ONNXRuntime 可用 providers: {providers}")
    if 'CUDAExecutionProvider' in providers:
        logger.success("ONNXRuntime 已检测到 CUDAExecutionProvider (GPU 支持)！")
        # 获取 ONNXRuntime CUDA 版本信息
        sess_options = ort.SessionOptions()
        sess = ort.InferenceSession(sess_options, providers=['CUDAExecutionProvider'])
        try:
            provider_options = sess.get_provider_options()
            logger.info(f"ONNXRuntime CUDA Provider 选项: {provider_options}")
        except Exception as e:
            logger.error(f"获取 ONNXRuntime Provider 选项失败: {e}")
    else:
        logger.warning("ONNXRuntime 未检测到 CUDAExecutionProvider，仅支持 CPU。")
        # 尝试找出原因
        logger.info("正在检查 ONNXRuntime CUDA 依赖...")
        onnx_module_path = os.path.dirname(ort.__file__)
        logger.info(f"ONNXRuntime 模块路径: {onnx_module_path}")
        cuda_provider_path = os.path.join(onnx_module_path, 'capi', 'onnxruntime_providers_cuda.dll')
        if os.path.exists(cuda_provider_path):
            logger.info(f"找到 CUDA Provider DLL: {cuda_provider_path}")
            check_dll_dependencies(cuda_provider_path)
        else:
            logger.warning(f"未找到 CUDA Provider DLL: {cuda_provider_path}")
except ImportError as e:
    logger.warning(f"未安装 onnxruntime，跳过 ONNXRuntime 检测: {e}")
except Exception as e:
    logger.error(f"ONNXRuntime GPU 检测失败: {e}")
    logger.error(traceback.format_exc())

# 检查cudnn
try:
    logger.info("正在检查 cuDNN 支持...")
    # 首先检查 cudnn64_9.dll 是否在 PATH 中
    cudnn_dll_paths = check_dll_in_paths('cudnn64_9.dll')
    
    if cudnn_dll_paths:
        # 尝试从找到的路径加载
        cudnn = try_load_dll_with_dependencies('cudnn64_9.dll', search_paths=[os.path.dirname(p) for p in cudnn_dll_paths])
        if cudnn:
            logger.success("cudnn64_9.dll 加载成功！cuDNN 9.x 可用。")
    else:
        # 尝试直接加载，看详细错误
        cudnn = try_load_dll_with_dependencies('cudnn64_9.dll')
        if cudnn:
            logger.success("cudnn64_9.dll 加载成功！cuDNN 9.x 可用。")
        else:
            logger.error("无法加载 cudnn64_9.dll")
            
            # 检查 CUDA 目录中的其他 cuDNN 版本
            if cuda_path:
                cuda_bin = os.path.join(cuda_path, 'bin')
                logger.info(f"检查 CUDA bin 目录中的 cuDNN DLL: {cuda_bin}")
                if os.path.exists(cuda_bin):
                    cudnn_files = [f for f in os.listdir(cuda_bin) if f.startswith('cudnn')]
                    if cudnn_files:
                        logger.info(f"在 CUDA bin 目录中找到以下 cuDNN 文件: {cudnn_files}")
                        # 尝试加载其他版本
                        for cudnn_file in cudnn_files:
                            try:
                                logger.info(f"尝试加载 {cudnn_file}...")
                                cudnn = ctypes.cdll.LoadLibrary(os.path.join(cuda_bin, cudnn_file))
                                logger.success(f"成功加载 {cudnn_file}！")
                                break
                            except Exception as e:
                                logger.error(f"加载 {cudnn_file} 失败: {e}")
                    else:
                        logger.warning(f"在 CUDA bin 目录中未找到任何 cuDNN 文件")
                else:
                    logger.warning(f"CUDA bin 目录不存在: {cuda_bin}")
except Exception as e:
    logger.error(f"cuDNN 检测失败: {e}")
    logger.error(traceback.format_exc())

# 检查是否存在 cublasLt64_12.dll (onnxruntime-gpu 需要的)
try:
    logger.info("正在检查 cublasLt64_12.dll (ONNXRuntime CUDA 依赖)...")
    cublas_paths = check_dll_in_paths('cublasLt64_12.dll')
    if cublas_paths:
        cublas = try_load_dll_with_dependencies('cublasLt64_12.dll')
        if cublas:
            logger.success("cublasLt64_12.dll 加载成功！")
    else:
        logger.warning("未找到 cublasLt64_12.dll，这可能导致 ONNXRuntime GPU 加速不可用")
        
        # 尝试检查是否有其他版本的 cublasLt
        if cuda_path:
            cuda_bin = os.path.join(cuda_path, 'bin')
            if os.path.exists(cuda_bin):
                cublas_files = [f for f in os.listdir(cuda_bin) if f.startswith('cublasLt')]
                if cublas_files:
                    logger.info(f"在 CUDA bin 目录中找到以下 cuBLAS 文件: {cublas_files}")
                else:
                    logger.warning(f"在 CUDA bin 目录中未找到任何 cuBLAS 文件")
except Exception as e:
    logger.error(f"cublasLt 检测失败: {e}")
    logger.error(traceback.format_exc())

logger.info("=== 检测结束 ===")

# 打印摘要信息
print("\n=== 检测摘要 ===")
print(f"CUDA_PATH: {cuda_path}")
try:
    import torch
    print(f"PyTorch: {torch.__version__}, CUDA 可用: {torch.cuda.is_available()}")
except:
    print("PyTorch: 未安装")
try:
    import onnxruntime as ort
    print(f"ONNXRuntime: {ort.__version__}, GPU 支持: {'CUDAExecutionProvider' in ort.get_available_providers()}")
except:
    print("ONNXRuntime: 未安装")
print(f"日志文件: {config_info['log_file']}")
print("检查详细日志获取更多信息\n") 