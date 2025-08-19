# 相似图片导出功能使用说明

## 功能概述

新增的相似图片导出功能可以：
1. 根据汉明距离阈值筛选相似图片对
2. 将相似图片组织成组
3. 每组内按文件名升序排序，保留第一个文件
4. 生成删除文件列表，用于批量删除重复图片

## 主要函数

### 1. `find_similar_groups(pairs, threshold)`
- **功能**: 根据阈值找出相似图片组
- **参数**: 
  - `pairs`: 图片对列表 `[(img1, img2, distance), ...]`
  - `threshold`: 汉明距离阈值，小于等于此值认为相似
- **返回**: 相似图片组列表

### 2. `export_similar_groups(results, threshold, output_dir, hash_size=None)`
- **功能**: 导出相似组，生成保留和删除文件列表
- **参数**:
  - `results`: `benchmark_phash_sizes` 的结果
  - `threshold`: 汉明距离阈值
  - `output_dir`: 输出目录
  - `hash_size`: 指定使用哪个哈希尺寸的结果
- **返回**: 包含保留文件、删除文件等信息的字典

## 使用方式

### 方式1: 在主程序中使用
运行 `size_preview.py`，程序会在生成HTML报告后询问是否导出相似组：

```bash
python size_preview.py
```

程序会引导您：
1. 选择要使用的哈希尺寸结果
2. 输入汉明距离阈值（程序会根据数据统计给出建议值）
3. 自动生成各种输出文件

### 方式2: 使用独立导出脚本
运行专门的导出脚本：

```bash
python export_similar.py
```

## 输出文件说明

对于阈值为5、哈希尺寸为16的导出，会生成以下文件：

1. **`similar_groups_threshold_5_hashsize_16.json`** - 详细信息文件
   - 包含元数据、每个相似组的完整信息
   - JSON格式，便于程序处理

2. **`keep_files_threshold_5_hashsize_16.txt`** - 保留文件列表
   - 每行一个文件路径
   - 这些文件是每组中按名称排序的第一个

3. **`delete_files_threshold_5_hashsize_16.txt`** - 删除文件列表
   - 每行一个文件路径
   - 这些是建议删除的重复文件

4. **`delete_similar_files_threshold_5_hashsize_16.bat`** - Windows批处理删除脚本
   - 可直接运行进行批量删除
   - 包含安全提示和确认步骤

## 阈值设置建议

- **阈值 0-2**: 非常严格，只有几乎完全相同的图片才会被认为相似
- **阈值 3-5**: 严格，适合删除明显的重复图片
- **阈值 6-10**: 中等，可能包含轻微变化的图片（如压缩、尺寸调整）
- **阈值 >10**: 宽松，可能包含相似但不完全相同的图片

程序会根据数据集的汉明距离分布自动建议合适的阈值。

## 安全注意事项

1. **务必检查删除列表**: 在执行删除前，请仔细检查 `delete_files_*.txt` 中的文件
2. **备份重要文件**: 建议在删除前备份重要文件
3. **测试小范围**: 可以先在小的测试目录上试用功能
4. **手动确认**: 对于重要的图片集合，建议手动确认相似组的分类

## 使用示例

```python
# 在你的代码中使用
from size_preview import benchmark_phash_sizes, export_similar_groups

# 计算哈希
results, image_files = benchmark_phash_sizes("your_image_folder", hash_sizes=(16,))

# 导出阈值为5的相似组
export_result = export_similar_groups(
    results, 
    threshold=5, 
    output_dir="your_output_folder",
    hash_size=16
)

print(f"找到 {len(export_result['groups'])} 个相似组")
print(f"建议删除 {len(export_result['delete_files'])} 个文件")
```

## 高级用法

### 自定义筛选策略
如果需要不同的文件保留策略，可以修改 `export_similar_groups` 函数中的排序逻辑：

```python
# 当前：按文件名排序
sorted_files = sorted(list(group), key=lambda x: Path(x).name.lower())

# 可以改为按文件大小排序（保留最大的）
sorted_files = sorted(list(group), key=lambda x: Path(x).stat().st_size, reverse=True)

# 或按修改时间排序（保留最新的）
sorted_files = sorted(list(group), key=lambda x: Path(x).stat().st_mtime, reverse=True)
```

这样可以根据具体需求选择保留哪个文件。
