# JSON到SQLite数据库迁移工具

此目录包含了将JSON哈希文件迁移到SQLite数据库的工具脚本。

## 文件说明

### 迁移脚本

- **`quick_migrate.py`** - 快速迁移脚本，自动迁移配置文件中的JSON文件
- **`migrate_json_to_sqlite.py`** - 完整功能的迁移脚本，支持多种选项和参数
- **`migrate.bat`** - Windows批处理脚本，用于快速执行迁移

### 使用方法

#### 1. 快速迁移（推荐）

最简单的方式是使用快速迁移脚本：

```bash
# 在项目根目录下运行
python -c "from src.hashu.utils.quick_migrate import quick_migrate; quick_migrate()"

# 或者直接运行脚本
cd src/hashu/utils
python quick_migrate.py
```

在Windows上可以直接双击运行：
```batch
src\hashu\utils\migrate.bat
```

#### 2. 完整功能迁移

如果需要更多控制选项，使用完整的迁移脚本：

```bash
# 迁移指定文件
python src/hashu/utils/migrate_json_to_sqlite.py /path/to/hash_file.json

# 迁移多个文件
python src/hashu/utils/migrate_json_to_sqlite.py file1.json file2.json

# 迁移目录中的所有JSON文件
python src/hashu/utils/migrate_json_to_sqlite.py /path/to/hash_directory/

# 使用配置文件中的默认JSON文件
python src/hashu/utils/migrate_json_to_sqlite.py --use-config

# 强制迁移（覆盖已存在的记录）
python src/hashu/utils/migrate_json_to_sqlite.py --force file.json

# 指定数据库路径
python src/hashu/utils/migrate_json_to_sqlite.py --db-path /custom/path/hash.db file.json

# 试运行（不实际执行迁移）
python src/hashu/utils/migrate_json_to_sqlite.py --dry-run --use-config

# 详细输出
python src/hashu/utils/migrate_json_to_sqlite.py --verbose --use-config
```

## 支持的JSON格式

### 新格式（推荐）
```json
{
  "_hash_params": "hash_size=10;hash_version=1",
  "hashes": {
    "archive://path/to/archive.zip!/image.jpg": {
      "hash": "1234567890abcdef",
      "size": 10,
      "timestamp": 1627123456.789,
      "file_size": 123456,
      "dimensions": [1920, 1080]
    }
  }
}
```

### 旧格式（兼容）
```json
{
  "_hash_params": "hash_size=10",
  "archive://path/to/archive.zip!/image.jpg": {
    "hash": "1234567890abcdef",
    "size": 10
  }
}
```

## 迁移特性

### 数据处理
- **URI解析**: 自动解析和分类不同类型的URI（文件路径、archive://协议、URL等）
- **重复处理**: 使用`INSERT OR REPLACE`策略处理重复记录
- **元数据保存**: 保留原始JSON中的所有元数据
- **时间戳**: 记录迁移时间和原始计算时间

### 性能优化
- **批量插入**: 使用批量操作提高迁移速度
- **索引优化**: 自动创建性能优化索引
- **事务处理**: 确保数据一致性

### 错误处理
- **文件验证**: 迁移前验证JSON文件格式
- **错误恢复**: 单个文件失败不影响其他文件迁移
- **详细日志**: 提供详细的迁移过程日志

## 迁移后验证

迁移完成后，可以使用以下方式验证数据：

```python
from hashu.core.sqlite_storage import HashDatabaseManager

# 获取数据库统计
db = HashDatabaseManager()
stats = db.get_statistics()
print(f"总记录数: {stats['total_records']}")
print(f"数据库大小: {stats['db_size_mb']} MB")

# 按来源类型统计
for source_type, count in stats['by_source_type'].items():
    print(f"{source_type}: {count} 条")
```

## 注意事项

1. **备份原始数据**: 迁移前建议备份原始JSON文件
2. **磁盘空间**: 确保有足够的磁盘空间存储SQLite数据库
3. **配置文件**: 确保`config.json`配置正确
4. **权限**: 确保对数据库文件目录有写权限

## 性能参考

基于测试数据：
- **迁移速度**: 约25,000条记录/秒
- **存储效率**: SQLite数据库大小约为原始JSON文件的1.5-2倍
- **查询性能**: 相比JSON文件查询速度提升10-100倍

## 故障排除

### 常见问题

1. **导入错误**: 确保项目根目录在Python路径中
2. **配置文件不存在**: 检查`src/hashu/config/config.json`
3. **权限错误**: 确保对数据库文件目录有读写权限
4. **内存不足**: 对于大型JSON文件，考虑分批迁移

### 日志文件

迁移过程会生成详细的日志文件，位于：
```
src/hashu/logs/migrate_json_to_sqlite_<timestamp>.log
```

可以查看日志文件获取详细的错误信息和迁移统计。
