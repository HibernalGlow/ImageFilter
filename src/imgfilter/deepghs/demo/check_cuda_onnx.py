import os
import sys

print("=== CUDA/cuDNN/ONNXRuntime GPU 检测 ===")

# 检查CUDA环境变量
cuda_path = os.environ.get('CUDA_PATH')
print(f"CUDA_PATH: {cuda_path}")

# 检查PATH中是否包含CUDA和cuDNN
path = os.environ.get('PATH', '')
print("\nPATH中包含以下CUDA/cuDNN相关路径:")
for p in path.split(';'):
    if 'cuda' in p.lower() or 'cudnn' in p.lower():
        print(f"  {p}")

# 检查CUDA驱动
try:
    import torch
    print(f"\nPyTorch 检测: CUDA 可用: {torch.cuda.is_available()}  设备数: {torch.cuda.device_count()}")
    if torch.cuda.is_available():
        print(f"  当前设备: {torch.cuda.get_device_name(0)}")
except ImportError:
    print("未安装 torch，跳过 PyTorch 检测")

# 检查onnxruntime GPU
try:
    import onnxruntime as ort
    providers = ort.get_available_providers()
    print(f"\nONNXRuntime 可用 providers: {providers}")
    if 'CUDAExecutionProvider' in providers:
        print("ONNXRuntime 已检测到 CUDAExecutionProvider (GPU 支持)！")
    else:
        print("ONNXRuntime 未检测到 CUDAExecutionProvider，仅支持 CPU。")
except ImportError:
    print("未安装 onnxruntime，跳过 ONNXRuntime 检测")

# 检查cudnn
try:
    import ctypes
    cudnn = ctypes.cdll.LoadLibrary('cudnn64_9.dll')
    print("cudnn64_9.dll 加载成功！cuDNN 9.x 可用。")
except Exception as e:
    print(f"cudnn64_9.dll 加载失败: {e}")

print("\n=== 检测结束 ===") 