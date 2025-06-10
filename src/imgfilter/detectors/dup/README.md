# LPIPS 图像特征提取与相似度计算

本模块提供了基于深度学习的图像特征提取和相似度计算功能，用于查找相似图像。相比传统的LPIPS方法，该实现具有以下优势：

1. **特征缓存**：自动保存每个图像的特征向量，避免重复计算
2. **高效模型**：使用EfficientNet-B0作为特征提取器，提供良好的性能和速度平衡
3. **多进程加速**：支持多进程并行计算图像特征距离
4. **GPU加速**：支持GPU加速特征提取和距离计算

## 安装依赖

首先需要安装所需的依赖项：

```bash
python install_deps.py
```

主要依赖包括：
- torch
- torchvision
- timm
- pillow-avif
- pillow-jxl

## 使用演示

提供了一个演示脚本`lpips_demo.py`，可以用来测试特征提取、缓存功能和相似图像查找：

```bash
# 使用方法
python lpips_demo.py <图片文件夹路径> [--mode {extract,cache,similar,all}] [--threshold 0.1] [--gpu] [--max-images 20]
```

参数说明：
- `folder`：图片文件夹路径
- `--mode`：测试模式，可选值：
  - `extract`：仅测试特征提取
  - `cache`：仅测试缓存功能
  - `similar`：仅测试相似图片查找
  - `all`：测试所有功能（默认）
- `--threshold`：相似度阈值，默认0.1，值越小要求越相似
- `--gpu`：是否使用GPU加速
- `--max-images`：最大处理图片数量，默认20

示例：

```bash
# 测试所有功能，使用GPU，最多处理50张图片
python lpips_demo.py D:\Pictures --gpu --max-images 50

# 只测试相似图片查找，阈值设为0.15
python lpips_demo.py D:\Pictures --mode similar --threshold 0.15
```

## 在代码中使用

### 特征提取

```python
from imgfilter.detectors.dup.lpips import extract_features

# 提取图像特征
feature = extract_features("path/to/image.jpg", use_gpu=True)
```

### 查找相似图像

```python
from imgfilter.detectors.dup.lpips import find_similar_images_by_lpips

# 图像文件列表
image_files = ["image1.jpg", "image2.jpg", "image3.jpg", ...]

# 查找相似图像组
similar_groups = find_similar_images_by_lpips(
    image_files,
    lpips_threshold=0.1,  # 相似度阈值
    use_gpu=True,         # 使用GPU
    lpips_max_workers=8   # 最大工作进程数
)

# 处理结果
for group in similar_groups:
    print(f"找到相似图像组，共{len(group)}张图片:")
    for img_path in group:
        print(f"  - {img_path}")
```

## 性能优化建议

1. 对于大量图像，建议先提取并缓存所有特征，然后再进行相似度比较
2. 使用GPU可以显著加速特征提取过程
3. 根据CPU核心数调整`lpips_max_workers`参数
4. 调整阈值`lpips_threshold`以获得最佳的相似图像匹配效果 