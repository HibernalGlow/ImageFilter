# pHash汉明距离测试工具

这个工具用于测试不同尺寸的pHash（感知哈希）算法的汉明距离极差，帮助用户找到最适合其图像相似度检测任务的pHash尺寸和汉明距离阈值。

## 背景

pHash（感知哈希）是一种常用于图像相似度检测的算法。通过pHash计算出的哈希值可以通过汉明距离（不同位的数量）来衡量两张图片的相似度。不同尺寸的pHash在不同场景下有不同的表现，本工具帮助您找到最适合您应用场景的配置。

## 功能

- 支持多种pHash尺寸测试（如8x8, 10x10, 12x12, 16x16等）
- 查找图像目录中的相似图片组
- 基于文件大小的质量过滤（保留最大文件）
- 计算不同pHash尺寸下的汉明距离统计指标
- 生成不同阈值下的相似度匹配率分析
- 可视化分析结果，生成统计图表

## 安装依赖

```bash
pip install -r requirements.txt
```

或者手动安装必要的依赖：

```bash
pip install numpy pillow imagehash matplotlib
```

## 使用方法

### 基本用法

```bash
python phash_demo.py --dir <图片目录>
```

### 高级选项

```bash
python phash_demo.py --dir <图片目录> --sizes 8,10,12,16 --threshold 10 --output phash_analysis.json
```

参数说明：
- `--dir`: 图片目录路径（必需）
- `--sizes`: pHash尺寸列表，用逗号分隔，默认为"8,10,12,16"
- `--threshold`: 汉明距离阈值，默认为10
- `--output`: 分析结果输出文件路径，默认为"phash_analysis.json"

### 可视化分析结果

生成分析结果后，可以使用可视化脚本生成图表：

```bash
python visualize_results.py --input phash_analysis.json --output charts
```

参数说明：
- `--input`: 分析结果JSON文件路径，默认为"phash_analysis.json"
- `--output`: 图表输出目录，默认为"charts"

此脚本将生成以下图表：
1. 汉明距离统计图（最小、最大、平均、中位数距离）
2. 不同阈值下的匹配率曲线图
3. 匹配率热力图
4. 汉明距离标准差柱状图

## 输出结果

工具会生成一个JSON格式的分析报告，包含以下内容：

1. 每种pHash尺寸的汉明距离统计：
   - 最小距离
   - 最大距离
   - 平均距离
   - 中位数距离
   - 标准差
   - 样本数量

2. 不同阈值下的匹配率：
   - 阈值2的匹配率
   - 阈值5的匹配率
   - 阈值8的匹配率
   - 阈值10的匹配率
   - 阈值12的匹配率
   - 阈值15的匹配率
   - 阈值20的匹配率

## 结果解读

较大的pHash尺寸（如16x16）通常具有更高的区分度，但对于相似图片可能会产生较大的汉明距离。较小的尺寸（如8x8）对细节不敏感，可能会将不太相似的图片也判断为相似。

选择合适的pHash尺寸和汉明距离阈值需要根据您的应用场景进行平衡：
- 如果需要严格的相似度检测（减少误报），可以选择较大的pHash尺寸和较小的汉明距离阈值
- 如果需要宽松的相似度检测（减少漏报），可以选择较小的pHash尺寸和较大的汉明距离阈值

### 解读匹配率热力图

匹配率热力图是一个非常直观的工具，帮助您选择最佳的pHash尺寸和汉明距离阈值组合：

- X轴表示不同的pHash尺寸
- Y轴表示不同的汉明距离阈值
- 色块中的数值表示在该配置下的匹配率（百分比）

通常，您会希望在保持足够高匹配率的同时，使用较大的pHash尺寸和较小的汉明距离阈值，这样可以减少误报。

## 示例

对于大多数通用场景，建议从以下配置开始测试：
- pHash尺寸：8或10
- 汉明距离阈值：10或12

## 工作流程建议

1. 使用默认参数运行工具，获取初步分析结果：
   ```bash
   python phash_demo.py --dir <图片目录>
   ```

2. 可视化分析结果：
   ```bash
   python visualize_results.py
   ```

3. 根据可视化结果，调整pHash尺寸和汉明距离阈值，重新运行测试：
   ```bash
   python phash_demo.py --dir <图片目录> --sizes 8,10,12 --threshold 12
   ```

4. 重复步骤2-3，直到找到最适合您应用场景的参数配置

# 图片宽度/高度过滤工具

一个用于按照图片尺寸筛选和分类图片的工具。

## 功能特点

- 支持按照图片宽度和高度进行筛选
- 支持多种尺寸规则配置
- 可以将图片分类到不同的文件夹
- 支持复制或移动操作
- 支持通过预设配置快速切换不同筛选方案

## 预设配置文件

预设配置文件 `presets.json` 位于程序同目录下，可以直接编辑这个文件来自定义筛选规则。

### 预设配置格式

```json
{
    "预设名称": {
        "description": "预设描述",
        "source_dir": "源目录路径",
        "target_dir": "目标目录路径",
        "dimension_rules": [
            {
                "min_width": 最小宽度,
                "max_width": 最大宽度 (-1 表示不限),
                "min_height": 最小高度 (-1 表示不限),
                "max_height": 最大高度 (-1 表示不限),
                "mode": "匹配模式 (and 或 or)",
                "folder": "目标子文件夹"
            },
            // 更多规则...
        ],
        "cut_mode": false, // false 为复制，true 为移动
        "max_workers": 16, // 并行处理线程数
        "threshold_count": 3 // 匹配阈值
    }
}
```

### 规则优先级

**重要说明**: 尺寸规则按照在配置中的顺序从上到下依次检查，优先级从高到低。一旦图片匹配到一个规则，就不会再检查后续规则。

例如，如果有两个规则：
1. 规则1: 宽度 0-900px
2. 规则2: 宽度 901-1800px

那么一张宽度为 800px 的图片只会匹配规则1，而不会再检查规则2。

### 匹配模式说明

- `"mode": "and"`: 图片的宽度和高度都必须满足条件才算匹配
- `"mode": "or"`: 图片的宽度或高度满足条件之一即算匹配

### 预设配置示例

```json
{
    "默认": {
        "description": "默认配置 - 大于等于1800像素宽度",
        "source_dir": "E:\\1Hub\\EH\\999EHV",
        "target_dir": "E:\\1Hub\\EH\\7EHV",
        "dimension_rules": [
            {
                "min_width": 1800,
                "max_width": -1,
                "min_height": -1,
                "max_height": -1,
                "mode": "or",
                "folder": ""
            }
        ],
        "cut_mode": false,
        "max_workers": 16,
        "threshold_count": 3
    },
    "双重分组": {
        "description": "双重分组 - 按不同宽度范围分组",
        "source_dir": "E:\\1Hub\\EH\\999EHV",
        "target_dir": "E:\\1Hub\\EH\\7EHV",
        "dimension_rules": [
            {
                "min_width": 0,
                "max_width": 900,
                "min_height": -1,
                "max_height": -1,
                "mode": "or",
                "folder": "900px"
            },
            {
                "min_width": 901,
                "max_width": 1800,
                "min_height": -1,
                "max_height": -1,
                "mode": "or",
                "folder": "1800px"
            }
        ],
        "cut_mode": false,
        "max_workers": 16,
        "threshold_count": 3
    }
}
```

## 使用方法

### 交互式使用

1. 运行程序 `python -m src.widthfilter -i`
2. 选择一个预设配置
3. 程序将按照选择的预设配置处理图片

### 命令行参数

```
python -m src.widthfilter [选项]

选项:
  -c, --clipboard      从剪贴板读取源目录路径
  -s, --source SOURCE  源目录路径
  -t, --target TARGET  目标目录路径
  -w, --width WIDTH    宽度阈值
  -l, --larger         选择大于等于指定宽度的文件
  -m, --move           移动文件而不是复制
  -j, --jobs JOBS      并行处理线程数
  -n, --number NUMBER  符合条件的图片数量阈值
  -i, --interactive    启用交互式选择预设
  -v, --version        显示版本信息
```

# 图像过滤器代码重构

## 重构内容

1. 提取重复的工具函数到 `src/imgfilter/detectors/utils.py`
   - 哈希计算相关函数
   - 图像数据获取函数
   - 哈希比较函数
   - 基于哈希的图像分组函数

2. 添加两阶段相似图片检测算法
   - 第一阶段：使用哈希(汉明距离)进行预分组
   - 第二阶段：对每个预分组内的图片进行LPIPS聚类

## 两阶段相似图片检测算法原理

### 问题背景

图像相似度比较中，LPIPS（Learned Perceptual Image Patch Similarity）提供了较高的感知准确度，但计算成本高昂。如果对所有图片两两进行LPIPS比较，时间复杂度为O(n²)，随着图片数量增加会变得非常慢。

### 解决方案

我们采用两阶段检测策略：

1. **第一阶段：快速哈希预分组**
   - 计算所有图片的感知哈希(pHash)
   - 使用汉明距离作为哈希相似度指标
   - 将汉明距离低于阈值的图片分到同一组
   - 时间复杂度近似O(n)，非常快速

2. **第二阶段：组内LPIPS聚类**
   - 只在每个哈希预分组内进行LPIPS聚类
   - 大大减少LPIPS计算次数
   - 保持最终聚类质量，同时显著提高性能

### 性能优势

假设有1000张图片，传统方法需要计算近50万次LPIPS距离。使用两阶段策略，如果平均每组有10张图片，则只需计算大约1万次LPIPS距离，性能提升约50倍。

### 使用方法

```python
# 使用默认参数的两阶段相似图片检测
detector = DuplicateImageDetector(
    hamming_threshold=12,  # 哈希预分组的汉明距离阈值
    lpips_threshold=0.02,  # LPIPS聚类的距离阈值
    use_gpu=True          # 是否使用GPU加速LPIPS计算
)

# 检测重复图片
duplicates, reasons = detector.detect_duplicates(
    image_files=image_list,
    mode='lpips'  # 使用LPIPS模式
)
```
