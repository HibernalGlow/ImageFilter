# 相似图片组过滤器

本模块提供多种策略用于处理相似图片组，帮助用户筛选出最有价值的图片，删除冗余图片。

## 主要功能

- **OCR文本分析**：识别图片中的文字，判断语言类型（中文、英文、日文等）
- **文字密度分析**：计算图片中文字占比和分布情况
- **多策略过滤**：支持基于时间、大小、OCR文本和组合策略的过滤

## 过滤策略

- **时间过滤**：保留最新创建/修改的图片
- **大小过滤**：保留文件大小最大的图片
- **OCR过滤**：保留文字内容最有价值的图片（基于语言优先级和文字密度）
- **混合过滤**：按顺序组合多种过滤策略（如OCR+时间、OCR+大小等）

## 文字密度分析

文字密度分析功能通过计算以下指标帮助判断图片中文本的价值：

- **文本区域占比**：文本区域面积占整个图片面积的比例
- **字符密度**：每1000像素中的字符数量
- **文本数量**：识别出的总字符数

这些指标有助于识别哪些图片包含更多有价值的文本信息，特别是在包含相同或相似内容的图片中。

## 使用方法

```python
from imgfilter.detectors.group import GroupFilter

# 创建过滤器实例
filter = GroupFilter()

# 假设有一组相似图片
similar_images = ["image1.jpg", "image2.png", "image3.webp"]

# 应用OCR过滤
to_delete, reasons = filter.process_by_ocr(similar_images)

# 应用混合过滤（OCR+时间+大小）
to_delete, reasons = filter.process_by_hybrid(similar_images, "ocr_time_size")

# 查看删除原因
for img in to_delete:
    print(f"将删除: {img}, 原因: {reasons[img]['details']}")
```

## OCR模块懒加载

OCR功能使用懒加载机制，只有在实际需要时才会导入相关依赖。这降低了基本使用的资源占用，并允许在不安装OCR依赖的情况下使用其他功能。 