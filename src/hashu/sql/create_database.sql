-- PostgreSQL 数据库创建脚本
-- 用于创建图片哈希存储系统的数据库和表结构

-- 创建数据库（如果不存在）
-- 注意：这个语句需要在 postgres 数据库中以超级用户身份执行
-- 或者使用管理工具创建数据库

-- 切换到目标数据库后执行以下语句

-- 创建主表：image_hashes
CREATE TABLE IF NOT EXISTS image_hashes (
    id BIGSERIAL PRIMARY KEY,
    uri VARCHAR(2048) NOT NULL UNIQUE,
    hash_value VARCHAR(128) NOT NULL,
    hash_size INTEGER NOT NULL DEFAULT 10,
    hash_version INTEGER NOT NULL DEFAULT 1,
    file_size BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    -- 新增字段用于改进查询功能
    filename VARCHAR(512),
    file_format VARCHAR(32),
    uri_without_format VARCHAR(2048),  -- 去掉格式的URL，用于优先匹配
    archive_name VARCHAR(512)  -- 压缩包名
);

-- 创建注释
COMMENT ON TABLE image_hashes IS '图片哈希值存储表';
COMMENT ON COLUMN image_hashes.id IS '主键ID';
COMMENT ON COLUMN image_hashes.uri IS '标准化的URI（file://或archive://协议）';
COMMENT ON COLUMN image_hashes.hash_value IS '图片的感知哈希值（16进制）';
COMMENT ON COLUMN image_hashes.hash_size IS '哈希大小（通常为10）';
COMMENT ON COLUMN image_hashes.hash_version IS '哈希算法版本';
COMMENT ON COLUMN image_hashes.file_size IS '文件大小（字节）';
COMMENT ON COLUMN image_hashes.created_at IS '记录创建时间';
COMMENT ON COLUMN image_hashes.updated_at IS '记录更新时间';
COMMENT ON COLUMN image_hashes.metadata IS '元数据（JSON格式）';
COMMENT ON COLUMN image_hashes.filename IS '文件名';
COMMENT ON COLUMN image_hashes.file_format IS '文件格式（如jpg、png等）';
COMMENT ON COLUMN image_hashes.uri_without_format IS '去掉格式的URL，用于格式转换时的匹配';
COMMENT ON COLUMN image_hashes.archive_name IS '压缩包名称';

-- 创建基础索引以优化查询性能
CREATE INDEX IF NOT EXISTS idx_image_hashes_uri ON image_hashes (uri);
CREATE INDEX IF NOT EXISTS idx_image_hashes_hash_value ON image_hashes (hash_value);
CREATE INDEX IF NOT EXISTS idx_image_hashes_created_at ON image_hashes (created_at);
CREATE INDEX IF NOT EXISTS idx_image_hashes_hash_size_version ON image_hashes (hash_size, hash_version);

-- 新增索引用于优化查询
CREATE INDEX IF NOT EXISTS idx_image_hashes_uri_without_format ON image_hashes (uri_without_format);
CREATE INDEX IF NOT EXISTS idx_image_hashes_filename ON image_hashes (filename);
CREATE INDEX IF NOT EXISTS idx_image_hashes_file_format ON image_hashes (file_format);
CREATE INDEX IF NOT EXISTS idx_image_hashes_archive_name ON image_hashes (archive_name);

-- 为新增字段创建复合索引，用于优化查询
CREATE INDEX IF NOT EXISTS idx_image_hashes_format_search ON image_hashes (uri_without_format, file_format);
CREATE INDEX IF NOT EXISTS idx_image_hashes_archive_file ON image_hashes (archive_name, filename);

-- 创建哈希值相似度查询的索引（用于汉明距离计算）
CREATE INDEX IF NOT EXISTS idx_image_hashes_hash_btree ON image_hashes USING btree (hash_value);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 删除已存在的触发器（如果有）
DROP TRIGGER IF EXISTS update_image_hashes_updated_at ON image_hashes;

-- 创建触发器
CREATE TRIGGER update_image_hashes_updated_at
    BEFORE UPDATE ON image_hashes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建统计视图
CREATE OR REPLACE VIEW image_hashes_stats AS
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT hash_value) as unique_hashes,
    COUNT(DISTINCT file_format) as unique_formats,
    COUNT(DISTINCT archive_name) as unique_archives,
    MIN(created_at) as earliest_record,
    MAX(created_at) as latest_record,
    AVG(file_size) as avg_file_size,
    SUM(file_size) as total_file_size
FROM image_hashes;

COMMENT ON VIEW image_hashes_stats IS '图片哈希统计视图';

-- 创建文件格式统计视图
CREATE OR REPLACE VIEW format_distribution AS
SELECT 
    file_format,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage,
    AVG(file_size) as avg_size
FROM image_hashes 
WHERE file_format IS NOT NULL
GROUP BY file_format
ORDER BY count DESC;

COMMENT ON VIEW format_distribution IS '文件格式分布统计';

-- 创建压缩包统计视图
CREATE OR REPLACE VIEW archive_distribution AS
SELECT 
    archive_name,
    COUNT(*) as file_count,
    COUNT(DISTINCT file_format) as format_count,
    SUM(file_size) as total_size,
    MIN(created_at) as first_added,
    MAX(created_at) as last_added
FROM image_hashes 
WHERE archive_name IS NOT NULL
GROUP BY archive_name
ORDER BY file_count DESC;

COMMENT ON VIEW archive_distribution IS '压缩包文件分布统计';

-- 创建函数：计算汉明距离
CREATE OR REPLACE FUNCTION hamming_distance(hash1 text, hash2 text)
RETURNS integer AS $$
BEGIN
    -- 将16进制哈希转换为bigint并计算异或，然后计算设置位的数量
    RETURN bit_count(('x' || hash1)::bit(64)::bigint # ('x' || hash2)::bit(64)::bigint);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION hamming_distance IS '计算两个哈希值的汉明距离';

-- 创建函数：查找相似图片
CREATE OR REPLACE FUNCTION find_similar_images(target_hash text, max_distance integer DEFAULT 5)
RETURNS TABLE(
    uri text,
    hash_value text,
    filename text,
    file_format text,
    distance integer,
    file_size bigint,
    created_at timestamp with time zone
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ih.uri,
        ih.hash_value,
        ih.filename,
        ih.file_format,
        hamming_distance(ih.hash_value, target_hash) as distance,
        ih.file_size,
        ih.created_at
    FROM image_hashes ih
    WHERE hamming_distance(ih.hash_value, target_hash) <= max_distance
    ORDER BY distance, ih.created_at DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_similar_images IS '查找相似图片（基于汉明距离）';

-- 创建数据库版本表
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(20) NOT NULL,
    description TEXT,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 插入当前版本信息
INSERT INTO schema_version (version, description) 
VALUES ('2.0.0', '支持文件名、格式、去格式URL和压缩包名的增强版本')
ON CONFLICT DO NOTHING;

-- 创建性能优化建议的注释
COMMENT ON TABLE schema_version IS '数据库结构版本记录';

-- 输出创建完成信息
DO $$
BEGIN
    RAISE NOTICE '图片哈希数据库结构创建完成！';
    RAISE NOTICE '- 主表: image_hashes';
    RAISE NOTICE '- 统计视图: image_hashes_stats, format_distribution, archive_distribution';
    RAISE NOTICE '- 函数: hamming_distance, find_similar_images';
    RAISE NOTICE '- 版本表: schema_version';
END $$;
