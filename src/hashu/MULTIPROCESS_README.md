# 多进程哈希计算优化指南

## 概述

hashu模块已经优化以支持多进程环境，通过预加载缓存、线程安全的缓存管理和可配置的保存策略来提高性能并避免文件写入冲突。

## 主要优化功能

### 1. 线程安全的缓存管理
- 使用递归锁（RLock）保护缓存操作
- 单例模式确保缓存一致性
- 支持缓存预加载和按需刷新

### 2. 多进程配置选项
```python
MULTIPROCESS_CONFIG = {
    'enable_auto_save': True,     # 是否启用自动保存
    'enable_global_cache': True,  # 是否启用全局缓存查询
    'preload_cache': None,        # 预加载的缓存字典
}
```

### 3. 优化的哈希计算方法
- 支持预加载缓存查询
- 可配置的自动保存策略
- 性能计数器和统计信息

## 使用方法

### 基本使用

```python
from hashu.core.calculate_hash_custom import ImageHashCalculator, HashCache

# 单进程环境（默认配置）
result = ImageHashCalculator.calculate_phash("image.jpg")
print(result['hash'])
```

### 多进程环境配置

```python
from hashu.utils.hash_process_config import setup_multiprocess_hash_environment
from hashu.core.calculate_hash_custom import ImageHashCalculator, HashCache

# 配置多进程环境
setup_multiprocess_hash_environment(
    enable_auto_save=False,        # 关闭自动保存避免冲突
    enable_global_cache=True,      # 启用全局缓存查询
    preload_cache_from_files=True  # 预加载缓存文件
)

# 在工作进程中使用
result = ImageHashCalculator.calculate_phash(
    "image.jpg",
    auto_save=False,    # 多进程下关闭自动保存
    use_preload=True    # 使用预加载缓存
)
```

### 批量多进程处理

```python
from hashu.utils.multiprocess_example import batch_calculate_hashes_multiprocess

# 图片路径列表
image_paths = ["img1.jpg", "img2.jpg", "img3.jpg"]

# 多进程批量计算
results = batch_calculate_hashes_multiprocess(
    image_paths, 
    max_workers=4
)

# 处理结果
for result in results:
    if result['success']:
        print(f"{result['path']}: {result['result']['hash']}")
    else:
        print(f"处理失败 {result['path']}: {result['error']}")
```

## 配置方法

### 1. 手动配置

```python
from hashu.core.calculate_hash_custom import HashCache

# 配置多进程环境
HashCache.configure_multiprocess(
    enable_auto_save=False,
    enable_global_cache=True,
    preload_cache=my_cache_dict  # 可选的预加载缓存
)

# 获取缓存统计
stats = HashCache.get_cache_stats()
print(f"缓存大小: {stats['cache_size']}")
print(f"多进程配置: {stats['multiprocess_config']}")
```

### 2. 使用配置工具

```python
from hashu.utils.hash_process_config import MultiProcessHashOptimizer

# 创建优化器
optimizer = MultiProcessHashOptimizer()

# 设置多进程环境
optimizer.setup_multiprocess_environment()

# 获取预加载的缓存
cache = optimizer.get_preloaded_cache()
print(f"预加载了 {len(cache)} 个哈希值")

# 恢复单进程配置
optimizer.configure_for_single_process()
```

## 性能测试

```python
from hashu.utils.multiprocess_example import compare_single_vs_multiprocess

# 比较单进程和多进程性能
compare_single_vs_multiprocess("/path/to/images", max_workers=4)
```

## 注意事项

### 多进程环境下的建议
1. **关闭自动保存**: 设置 `enable_auto_save=False` 避免文件写入冲突
2. **使用预加载缓存**: 设置 `use_preload=True` 提高缓存命中率
3. **合理设置进程数**: 通常设置为CPU核心数的1-2倍
4. **批量保存**: 在所有进程完成后统一保存结果

### 缓存管理
- 缓存会自动刷新，超时时间为30分钟（1800秒）
- 新计算的哈希值会累积到计数器，达到阈值时自动保存
- 可以手动调用 `HashCache.sync_to_file(force=True)` 强制保存

### 错误处理
- 所有方法都包含异常处理，失败时返回合理的默认值
- 使用loguru记录详细的调试信息
- 支持优雅降级，即使缓存加载失败也能正常工作

## 示例项目结构

```
src/
├── hashu/
│   ├── core/
│   │   └── calculate_hash_custom.py    # 核心哈希计算（已优化）
│   └── utils/
│       ├── hash_process_config.py      # 多进程配置工具
│       ├── multiprocess_example.py     # 使用示例
│       └── multiprocess_hash.py        # 独立的多进程模块
```

## 兼容性

- 保持向后兼容，现有代码无需修改即可正常工作
- 新的多进程功能是可选的，不会影响单进程使用
- 支持Python 3.8+
- 依赖库: PIL, imagehash, orjson, loguru

## 更新日志

- ✅ 添加线程安全的缓存管理
- ✅ 实现多进程配置选项
- ✅ 优化哈希计算方法支持预加载缓存
- ✅ 创建多进程配置工具和示例
- ✅ 添加性能测试和比较功能
- ✅ 完善错误处理和日志记录
