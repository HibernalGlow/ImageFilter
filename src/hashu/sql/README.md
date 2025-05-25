# 图片哈希数据库管理系统

这个目录包含了图片哈希存储系统的数据库管理工具和脚本。

## 📁 文件说明

### SQL文件
- `create_database.sql` - 数据库结构创建脚本
- `database_config.ini` - 数据库配置文件模板

### Python脚本
- `init_database.py` - 数据库初始化脚本
- `upgrade_database_schema.py` - 数据库结构升级脚本
- `migrate_to_postgresql.py` - JSON数据迁移脚本
- `database_manager.py` - 数据库管理工具
- `quick_setup.py` - 快速设置和测试脚本

### 批处理文件
- `manage_database.bat` - Windows批处理管理脚本

## 🚀 快速开始

### 1. 环境准备

确保已安装PostgreSQL和必要的Python包：

```bash
pip install asyncpg loguru orjson
```

设置环境变量（可选，也可以在命令中指定）：

```bash
# Windows
set POSTGRES_HOST=localhost
set POSTGRES_PORT=5432
set POSTGRES_USER=postgres
set POSTGRES_PASSWORD=your_password
set POSTGRES_DB=image_hashes

# Linux/Mac
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=your_password
export POSTGRES_DB=image_hashes
```

### 2. 一键设置和测试

运行快速设置脚本：

```bash
python quick_setup.py
```

这个脚本会：
- 检查环境配置
- 创建数据库（如果不存在）
- 初始化表结构
- 运行功能测试
- 提供使用说明

### 3. 使用Windows批处理工具

在Windows系统上，您可以直接运行：

```bash
manage_database.bat
```

这将启动一个交互式菜单，提供所有常用的数据库管理功能。

## 🔧 详细使用方法

### 初始化数据库

```bash
# 仅初始化表结构（假设数据库已存在）
python init_database.py

# 创建数据库并初始化结构
python init_database.py --create-db

# 使用自定义连接参数
python init_database.py --host=localhost --port=5432 --user=postgres --database=my_db

# 使用连接URL
python init_database.py --url="postgresql://user:pass@host:port/database"
```

### 管理数据库

```bash
# 查看数据库状态
python database_manager.py status

# 升级数据库结构
python database_manager.py upgrade

# 从JSON文件迁移数据
python database_manager.py migrate file1.json file2.json

# 清理重复记录
python database_manager.py cleanup

# 优化数据库性能
python database_manager.py optimize

# 导出统计信息
python database_manager.py export-stats --output=stats.json
```

### 迁移现有数据

如果您有现有的JSON哈希文件，可以使用迁移工具：

```bash
python migrate_to_postgresql.py --files=/path/to/hash1.json /path/to/hash2.json
```

## 📊 数据库结构

### 主表：image_hashes

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键ID |
| uri | VARCHAR(2048) | 标准化URI（file://或archive://协议） |
| hash_value | VARCHAR(128) | 图片感知哈希值（16进制） |
| hash_size | INTEGER | 哈希大小（默认10） |
| hash_version | INTEGER | 哈希算法版本 |
| file_size | BIGINT | 文件大小（字节） |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |
| metadata | JSONB | 元数据 |
| filename | VARCHAR(512) | 文件名 |
| file_format | VARCHAR(32) | 文件格式 |
| uri_without_format | VARCHAR(2048) | 去掉格式的URL |
| archive_name | VARCHAR(512) | 压缩包名 |

### 视图

- `image_hashes_stats` - 基本统计信息
- `format_distribution` - 文件格式分布
- `archive_distribution` - 压缩包分布

### 函数

- `hamming_distance(hash1, hash2)` - 计算汉明距离
- `find_similar_images(target_hash, max_distance)` - 查找相似图片

## 🎯 新功能特性

### 1. 优先格式匹配

支持根据去掉格式的URL进行匹配，方便图片格式转换：

```python
# 优先查找jpg、png、webp格式的图片
record = await db_storage.get_hash_with_format_priority(
    uri="file:///E:/image.gif", 
    preferred_formats=['jpg', 'png', 'webp']
)
```

### 2. 增强的URI解析

自动解析URI信息，提取文件名、格式、压缩包名等：

```python
from hashu.utils.path_uri import URIParser

uri_info = URIParser.parse_uri("archive:///E:/data.zip!folder/image.jpg")
# 返回: {
#   'filename': 'image.jpg',
#   'file_format': 'jpg', 
#   'uri_without_format': 'archive:///E:/data.zip!folder/image',
#   'archive_name': 'data.zip'
# }
```

### 3. 向下兼容

完全兼容现有的JSON格式数据，支持无缝迁移。

## 🔍 查询示例

### 基本查询

```sql
-- 查找特定格式的图片
SELECT * FROM image_hashes WHERE file_format = 'jpg';

-- 查找压缩包中的图片
SELECT * FROM image_hashes WHERE archive_name IS NOT NULL;

-- 按文件大小排序
SELECT filename, file_size FROM image_hashes ORDER BY file_size DESC LIMIT 10;
```

### 统计查询

```sql
-- 查看基本统计
SELECT * FROM image_hashes_stats;

-- 查看格式分布
SELECT * FROM format_distribution;

-- 查看压缩包分布  
SELECT * FROM archive_distribution;
```

### 相似度查询

```sql
-- 查找相似图片（汉明距离<=5）
SELECT * FROM find_similar_images('abc123def456', 5);

-- 手动计算汉明距离
SELECT hamming_distance('abc123', 'abc124');
```

## 🛠️ 维护和优化

### 定期维护

```bash
# 清理重复记录
python database_manager.py cleanup

# 优化数据库性能
python database_manager.py optimize

# 查看数据库状态
python database_manager.py status
```

### 性能调优

1. **索引优化**：数据库已创建必要的索引，支持高效查询
2. **连接池**：使用连接池管理数据库连接
3. **批量操作**：支持批量插入和查询，提高性能
4. **查询缓存**：可配置查询结果缓存

### 备份建议

```bash
# 使用pg_dump备份整个数据库
pg_dump -h localhost -U postgres -d image_hashes > backup.sql

# 仅备份结构
pg_dump -h localhost -U postgres -d image_hashes --schema-only > schema.sql

# 仅备份数据
pg_dump -h localhost -U postgres -d image_hashes --data-only > data.sql
```

## 🔧 配置文件

编辑 `database_config.ini` 文件来自定义数据库设置：

```ini
[database]
host = localhost
port = 5432
user = postgres
password = 
database = image_hashes

[features]
enable_format_priority_search = true
preferred_formats = jpg,png,webp,avif

[performance]
batch_insert_size = 1000
query_cache_size = 10000
```

## 🐛 故障排除

### 常见问题

1. **连接失败**
   - 检查PostgreSQL服务是否运行
   - 验证连接参数是否正确
   - 确认防火墙设置

2. **权限错误**
   - 确保用户有创建数据库的权限
   - 检查表和函数的访问权限

3. **迁移失败**
   - 检查JSON文件格式是否正确
   - 确认文件路径是否存在
   - 查看详细错误日志

### 日志和调试

启用详细日志：

```python
from loguru import logger
logger.add("debug.log", level="DEBUG")
```

检查PostgreSQL日志：
- Windows: `C:\Program Files\PostgreSQL\14\data\log\`
- Linux: `/var/log/postgresql/`

## 📄 许可证

此项目遵循与主项目相同的许可证。

## 🤝 贡献

欢迎提交问题报告和功能请求！
