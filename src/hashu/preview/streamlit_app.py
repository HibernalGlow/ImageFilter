import streamlit as st
import json
import time
from pathlib import Path
from PIL import Image
import pillow_avif
import pillow_jxl 
import imagehash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import base64
import io
import zipfile
import tempfile
import hashlib
import os
from functools import lru_cache

# 页面配置
st.set_page_config(
    page_title="pHash 图片相似度分析",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(90deg, #f0f2f6, #ffffff);
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }
    .stExpander > div > div > div > div {
        padding-top: 0.5rem;
    }
    .image-comparison {
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px;
        margin: 5px;
    }
    .distance-low { color: #d32f2f; font-weight: bold; }
    .distance-medium { color: #f57c00; font-weight: bold; }
    .distance-high { color: #388e3c; font-weight: bold; }
    
    /* 疑似重复图片组的样式 */
    .duplicate-group {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px;
        margin: 5px;
        background-color: #fafafa;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .duplicate-header {
        text-align: center;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 10px;
    }
    .vs-separator {
        text-align: center;
        font-weight: bold;
        color: #ff6b6b;
        margin: 5px 0;
    }
</style>
""", unsafe_allow_html=True)

def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # 默认配置
        return {
            "app_config": {
                "title": "pHash 图片相似度分析",
                "icon": "🔍",
                "layout": "wide",
                "max_images_display": 50,
                "thumbnail_size": [150, 150],
                "default_folder": "E:\\2EHV\\test"
            },
            "hash_presets": {
                "快速测试": [8, 10],
                "标准分析": [10, 12, 16],
                "精细分析": [12, 16, 20, 24],
                "全面分析": [8, 10, 12, 16, 20, 24, 32]
            },
            "available_sizes": [4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64],
            "distance_thresholds": {
                "very_similar": 5,
                "similar": 15,
                "different": 25
            },
            "image_extensions": [
                ".jpg", ".jpeg", ".png", ".webp", 
                ".bmp", ".gif", ".tiff", ".jxl", ".avif"
            ]
        }

def load_session_state():
    """初始化session state"""
    if 'results' not in st.session_state:
        st.session_state.results = {}
    if 'image_files' not in st.session_state:
        st.session_state.image_files = []
    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
    if 'hash_cache' not in st.session_state:
        st.session_state.hash_cache = {}

@st.cache_data(show_spinner=False)
def get_file_info(file_path):
    """获取文件信息用于缓存键"""
    try:
        stat = os.stat(file_path)
        return {
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'path': str(file_path)
        }
    except Exception:
        return None

def create_cache_key(file_path, hash_size):
    """创建缓存键"""
    file_info = get_file_info(file_path)
    if file_info is None:
        return None
    
    # 基于文件路径、大小、修改时间和哈希尺寸创建键
    cache_data = f"{file_info['path']}_{file_info['size']}_{file_info['mtime']}_{hash_size}"
    return hashlib.md5(cache_data.encode()).hexdigest()

@lru_cache(maxsize=1000)
def _calculate_single_phash(file_path_str, hash_size, cache_key):
    """计算单个图片的pHash（带LRU缓存）"""
    try:
        with Image.open(file_path_str) as im:
            return str(imagehash.phash(im, hash_size=hash_size))
    except Exception as e:
        st.warning(f"图片处理失败: {file_path_str}，原因: {e}")
        return None

def calculate_image_hash_cached(file_path, hash_size):
    """计算图片哈希（带缓存）"""
    file_path_str = str(file_path)
    cache_key = create_cache_key(file_path_str, hash_size)
    
    if cache_key is None:
        # 文件不存在或无法访问，直接计算
        try:
            with Image.open(file_path_str) as im:
                return str(imagehash.phash(im, hash_size=hash_size))
        except Exception as e:
            st.warning(f"图片处理失败: {file_path_str}，原因: {e}")
            return None
    
    # 检查session state缓存
    if cache_key in st.session_state.hash_cache:
        return st.session_state.hash_cache[cache_key]
    
    # 使用LRU缓存计算
    hash_value = _calculate_single_phash(file_path_str, hash_size, cache_key)
    
    # 存储到session state缓存
    if hash_value is not None:
        st.session_state.hash_cache[cache_key] = hash_value
    
    return hash_value

def scan_images(image_dir, config):
    """扫描图片文件"""
    image_dir = Path(image_dir)
    image_extensions = config["image_extensions"]
    image_files = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    status_text.text("正在扫描图片文件...")
    
    for ext in image_extensions:
        files = list(image_dir.rglob(f"*{ext}"))
        files.extend(list(image_dir.rglob(f"*{ext.upper()}")))
        image_files.extend(files)
    
    progress_bar.progress(1.0)
    status_text.text(f"扫描完成，共找到 {len(image_files)} 张图片")
    
    return image_files

def calc_hashes_for_images(image_files, hash_size):
    """计算图片哈希（使用缓存优化）"""
    hashes = {}
    total = len(image_files)
    cache_hits = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, img in enumerate(image_files):
        # 检查缓存
        cache_key = create_cache_key(str(img), hash_size)
        if cache_key and cache_key in st.session_state.hash_cache:
            # 缓存命中
            hashes[str(img)] = st.session_state.hash_cache[cache_key]
            cache_hits += 1
        else:
            # 计算新哈希
            hash_value = calculate_image_hash_cached(img, hash_size)
            if hash_value is not None:
                hashes[str(img)] = hash_value
        
        progress = (i + 1) / total
        progress_bar.progress(progress)
        status_text.text(f"计算哈希 ({hash_size}): {i + 1}/{total} (缓存命中: {cache_hits})")
    
    # 显示缓存统计
    if cache_hits > 0:
        cache_ratio = cache_hits / total * 100
        st.success(f"✅ 哈希计算完成！缓存命中率: {cache_ratio:.1f}% ({cache_hits}/{total})")
    
    return hashes

def calc_hamming_pairs(hashes):
    """计算汉明距离"""
    pairs = []
    items = list(hashes.items())
    total_pairs = len(items) * (len(items) - 1) // 2
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    processed = 0
    for i, (img1, h1_str) in enumerate(items):
        h1 = imagehash.hex_to_hash(h1_str)
        for j in range(i + 1, len(items)):
            img2, h2_str = items[j]
            h2 = imagehash.hex_to_hash(h2_str)
            dist = h1 - h2
            pairs.append({
                "image1": img1,
                "image2": img2,
                "distance": dist,
                "hash1": h1_str,
                "hash2": h2_str
            })
            
            processed += 1
            if processed % 100 == 0:  # 每100次更新一次进度
                progress = processed / total_pairs
                progress_bar.progress(progress)
                status_text.text(f"计算汉明距离: {processed}/{total_pairs}")
    
    progress_bar.progress(1.0)
    status_text.text(f"汉明距离计算完成: {total_pairs} 对")
    
    return pairs

def save_results_to_json(results, image_files, output_path):
    """保存结果到JSON文件"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "total_images": len(image_files),
        "image_files": [str(f) for f in image_files],
        "results": results
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return data

def load_results_from_json(json_path):
    """从JSON文件加载结果"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        st.error(f"加载JSON文件失败: {e}")
        return None

def get_image_base64(image_path, max_size=(150, 150)):
    """将图片转换为base64编码"""
    try:
        with Image.open(image_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            return f"data:image/png;base64,{img_str}"
    except:
        return None

def get_image_info(image_path):
    """获取图片的尺寸和文件大小信息"""
    try:
        if not Path(image_path).exists():
            return None
        
        # 获取文件大小
        file_size = Path(image_path).stat().st_size
        size_str = format_file_size(file_size)
        
        # 获取图片尺寸
        with Image.open(image_path) as img:
            width, height = img.size
            return {
                'size': file_size,
                'size_str': size_str,
                'width': width,
                'height': height,
                'dimensions': f"{width}×{height}"
            }
    except Exception:
        return None

def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def get_distance_color_class(distance, config):
    """根据距离返回CSS类名"""
    thresholds = config["distance_thresholds"]
    if distance <= thresholds["very_similar"]:
        return "distance-low"
    elif distance <= thresholds["similar"]:
        return "distance-medium"
    else:
        return "distance-high"

def export_results_excel(results, image_files):
    """导出结果到Excel文件"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 总体统计表
        summary_data = []
        for size, info in results.items():
            stats = info["statistics"]
            summary_data.append({
                "哈希尺寸": size,
                "计算耗时(秒)": info['elapsed_time'],
                "平均距离": stats['avg_distance'],
                "最大距离": stats['max_distance'],
                "最小距离": stats['min_distance'],
                "对比总数": stats['total_pairs']
            })
        
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='总体统计', index=False)
        
        # 每个尺寸的详细结果
        for size, info in results.items():
            pairs_data = []
            for pair in info["pairs"]:
                img1_path = Path(pair["image1"])
                img2_path = Path(pair["image2"])
                pairs_data.append({
                    "图片1名称": img1_path.name,
                    "图片1路径": str(img1_path),
                    "图片2名称": img2_path.name,
                    "图片2路径": str(img2_path),
                    "汉明距离": pair["distance"],
                    "哈希1": pair["hash1"],
                    "哈希2": pair["hash2"]
                })
            
            if pairs_data:
                df_pairs = pd.DataFrame(pairs_data)
                # 按距离排序
                df_pairs = df_pairs.sort_values('汉明距离')
                df_pairs.to_excel(writer, sheet_name=f'尺寸{size}', index=False)
    
    output.seek(0)
    return output

def create_duplicate_report(results, similarity_threshold=10):
    """生成疑似重复图片报告"""
    duplicates = {}
    
    for size, info in results.items():
        size_duplicates = []
        for pair in info["pairs"]:
            if pair["distance"] <= similarity_threshold:
                size_duplicates.append(pair)
        
        # 按汉明距离升序排序（最相似的在前面）
        size_duplicates.sort(key=lambda x: x["distance"])
        duplicates[size] = size_duplicates
    
    return duplicates

def clear_hash_cache():
    """清理哈希缓存"""
    if 'hash_cache' in st.session_state:
        cache_size = len(st.session_state.hash_cache)
        st.session_state.hash_cache.clear()
        _calculate_single_phash.cache_clear()  # 清理LRU缓存
        return cache_size
    return 0

def get_cache_info():
    """获取缓存信息"""
    session_cache_size = len(st.session_state.hash_cache) if 'hash_cache' in st.session_state else 0
    lru_cache_info = _calculate_single_phash.cache_info()
    
    return {
        'session_cache_entries': session_cache_size,
        'lru_cache_hits': lru_cache_info.hits,
        'lru_cache_misses': lru_cache_info.misses,
        'lru_cache_size': lru_cache_info.currsize,
        'lru_cache_max': lru_cache_info.maxsize
    }

def render_sidebar(config):
    """渲染侧边栏配置"""
    st.sidebar.title("⚙️ 配置选项")
    
    # 选择模式
    mode = st.sidebar.radio(
        "选择模式",
        ["新建分析", "加载已有结果"],
        help="选择新建分析或加载之前保存的结果"
    )
    
    return mode

def render_new_analysis_sidebar(config):
    """渲染新建分析模式的侧边栏配置"""
    app_config = config["app_config"]
    
    # 文件夹选择
    image_folder = st.sidebar.text_input(
        "📁 图片文件夹路径",
        value=app_config["default_folder"],
        help="输入包含图片的文件夹路径"
    )
    
    # 哈希尺寸选择
    st.sidebar.markdown("### 🎯 哈希尺寸设置")
    
    # 预设选项
    preset_options = ["自定义"] + list(config["hash_presets"].keys())
    preset_sizes = st.sidebar.selectbox(
        "预设尺寸组合",
        preset_options
    )
    
    if preset_sizes == "自定义":
        # 多选框选择尺寸
        selected_sizes = st.sidebar.multiselect(
            "选择哈希尺寸",
            config["available_sizes"],
            default=[10, 12, 16],
            help="选择要测试的哈希尺寸，可以选择多个"
        )
    else:
        selected_sizes = config["hash_presets"][preset_sizes]
        st.sidebar.info(f"已选择尺寸: {selected_sizes}")
    
    # 高级设置
    with st.sidebar.expander("🔧 高级设置"):
        similarity_threshold = st.slider(
            "疑似重复阈值",
            min_value=0,
            max_value=60,
            value=10,
            help="汉明距离小于此值的图片将被标记为疑似重复"
        )
        
        export_format = st.selectbox(
            "导出格式",
            ["JSON", "Excel"],
            help="选择结果导出格式"
        )
    
    return image_folder, selected_sizes, similarity_threshold, export_format

def handle_new_analysis(config, image_folder, selected_sizes, export_format):
    """处理新建分析逻辑"""
    if st.sidebar.button("🚀 开始分析", type="primary"):
        if not image_folder or not Path(image_folder).exists():
            st.error("请输入有效的图片文件夹路径！")
        elif not selected_sizes:
            st.error("请至少选择一个哈希尺寸！")
        else:
            execute_analysis(config, image_folder, selected_sizes, export_format)

def execute_analysis(config, image_folder, selected_sizes, export_format):
    """执行图片分析"""
    st.markdown("## 📊 分析进度")
    
    # 扫描图片
    with st.expander("📁 扫描图片文件", expanded=True):
        image_files = scan_images(image_folder, config)
        st.session_state.image_files = image_files
    
    if len(image_files) < 2:
        st.error("图片数量太少，需要至少2张图片进行对比分析！")
        return
    
    # 分析每个尺寸
    results = {}
    
    for size in selected_sizes:
        with st.expander(f"🔍 分析哈希尺寸 {size}", expanded=True):
            st.write(f"**哈希尺寸: {size}**")
            
            start_time = time.time()
            
            # 计算哈希
            st.write("计算图片哈希...")
            hashes = calc_hashes_for_images(image_files, size)
            
            # 计算汉明距离
            st.write("计算汉明距离...")
            pairs = calc_hamming_pairs(hashes)
            
            elapsed_time = time.time() - start_time
            
            # 统计信息
            distances = [p["distance"] for p in pairs]
            if distances:
                avg_dist = sum(distances) / len(distances)
                max_dist = max(distances)
                min_dist = min(distances)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("计算耗时", f"{elapsed_time:.2f}s")
                with col2:
                    st.metric("平均距离", f"{avg_dist:.2f}")
                with col3:
                    st.metric("最大距离", str(max_dist))
                with col4:
                    st.metric("最小距离", str(min_dist))
            
            results[size] = {
                "hashes": hashes,
                "pairs": pairs,
                "elapsed_time": elapsed_time,
                "statistics": {
                    "avg_distance": avg_dist if distances else 0,
                    "max_distance": max_dist if distances else 0,
                    "min_distance": min_dist if distances else 0,
                    "total_pairs": len(pairs)
                }
            }
    
    st.session_state.results = results
    st.session_state.analysis_complete = True
    
    # 保存结果
    output_path = Path(image_folder) / f"phash_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    if export_format == "JSON":
        save_results_to_json(results, image_files, output_path)
        st.success(f"✅ 分析完成！JSON结果已保存到: {output_path}")
    
    # 提供下载按钮
    if export_format == "Excel":
        excel_data = export_results_excel(results, image_files)
        st.download_button(
            label="📥 下载Excel报告",
            data=excel_data,
            file_name=f"phash_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def handle_load_results():
    """处理加载已有结果逻辑"""
    json_file = st.sidebar.file_uploader(
        "上传JSON结果文件",
        type=['json'],
        help="选择之前保存的分析结果文件"
    )
    
    if json_file is not None:
        data = json.load(json_file)
        st.session_state.results = data["results"]
        st.session_state.image_files = [Path(f) for f in data["image_files"]]
        st.session_state.analysis_complete = True
        
        st.sidebar.success(f"✅ 已加载 {data['total_images']} 张图片的分析结果")
        st.sidebar.info(f"分析时间: {data['timestamp']}")

def render_overall_analysis_tab():
    """渲染总体分析标签页"""
    # 总体对比表
    st.markdown("### 📊 总体统计")
    summary_data = []
    for size, info in st.session_state.results.items():
        stats = info["statistics"]
        summary_data.append({
            "哈希尺寸": size,
            "计算耗时(秒)": f"{info['elapsed_time']:.2f}",
            "平均距离": f"{stats['avg_distance']:.2f}",
            "最大距离": stats['max_distance'],
            "最小距离": stats['min_distance'],
            "对比总数": stats['total_pairs']
        })
    
    df_summary = pd.DataFrame(summary_data)
    st.dataframe(df_summary, use_container_width=True)
    
    # 可视化对比
    col1, col2 = st.columns(2)
    with col1:
        fig1 = px.bar(
            df_summary,
            x="哈希尺寸",
            y="平均距离",
            title="不同哈希尺寸的平均汉明距离对比",
            color="平均距离",
            color_continuous_scale="viridis"
        )
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        fig2 = px.bar(
            df_summary,
            x="哈希尺寸",
            y="计算耗时(秒)",
            title="不同哈希尺寸的计算耗时对比",
            color="计算耗时(秒)",
            color_continuous_scale="reds"
        )
        st.plotly_chart(fig2, use_container_width=True)

def render_detailed_comparison_tab(config):
    """渲染详细对比标签页"""
    app_config = config["app_config"]
    
    # 详细结果展示
    st.markdown("### 🔍 详细对比结果")
    
    for size, info in st.session_state.results.items():
        with st.expander(f"📋 哈希尺寸 {size} - 详细结果", expanded=False):
            pairs = info["pairs"]
            stats = info["statistics"]
            
            # 统计信息
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("总对比数", stats['total_pairs'])
            with col2:
                st.metric("平均距离", f"{stats['avg_distance']:.2f}")
            with col3:
                st.metric("最大距离", stats['max_distance'])
            with col4:
                st.metric("最小距离", stats['min_distance'])
            
            # 距离分布图
            distances = [p["distance"] for p in pairs]
            fig_hist = px.histogram(
                x=distances,
                nbins=30,
                title=f"哈希尺寸 {size} - 汉明距离分布",
                labels={"x": "汉明距离", "y": "频次"}
            )
            st.plotly_chart(fig_hist, use_container_width=True)
            
            # 过滤器
            st.markdown("#### 🔧 过滤选项")
            col1, col2 = st.columns(2)
            with col1:
                max_distance = st.slider(
                    f"最大汉明距离 (size {size})",
                    min_value=0,
                    max_value=stats['max_distance'],
                    value=min(10, stats['max_distance']),
                    key=f"filter_{size}"
                )
            with col2:
                show_images = st.checkbox(f"显示图片预览 (size {size})", key=f"show_img_{size}")
            
            # 过滤和排序
            filtered_pairs = [p for p in pairs if p["distance"] <= max_distance]
            filtered_pairs.sort(key=lambda x: x["distance"])
            
            st.write(f"**显示 {len(filtered_pairs)} 对相似图片 (距离 ≤ {max_distance})**")
            
            # 显示结果
            if show_images:
                render_image_pairs(filtered_pairs, config, app_config)
            else:
                render_pairs_table(filtered_pairs)

def render_image_pairs(filtered_pairs, config, app_config):
    """渲染图片对比显示"""
    # 图片展示模式
    max_display = app_config.get("max_images_display", 50)
    for i, pair in enumerate(filtered_pairs[:max_display]):
        distance = pair["distance"]
        img1_path = Path(pair["image1"])
        img2_path = Path(pair["image2"])
        
        st.markdown(f"**对比 {i+1}** - 汉明距离: "
                  f"<span class='{get_distance_color_class(distance, config)}'>{distance}</span>",
                  unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if img1_path.exists():
                st.image(str(img1_path), caption=img1_path.name, width=200)
            st.caption(f"📁 {img1_path.parent}")
        
        with col2:
            if img2_path.exists():
                st.image(str(img2_path), caption=img2_path.name, width=200)
            st.caption(f"📁 {img2_path.parent}")
        
        st.markdown("---")
    
    if len(filtered_pairs) > max_display:
        st.info(f"仅显示前 {max_display} 对，共有 {len(filtered_pairs)} 对符合条件")

def render_pairs_table(filtered_pairs):
    """渲染图片对比表格"""
    # 表格展示模式
    table_data = []
    for pair in filtered_pairs:
        img1_path = Path(pair["image1"])
        img2_path = Path(pair["image2"])
        table_data.append({
            "图片1": img1_path.name,
            "图片1路径": str(img1_path.parent),
            "图片2": img2_path.name,
            "图片2路径": str(img2_path.parent),
            "汉明距离": pair["distance"]
        })
    
    if table_data:
        df_pairs = pd.DataFrame(table_data)
        st.dataframe(df_pairs, use_container_width=True)

def render_duplicate_detection_tab(config):
    """渲染疑似重复图片标签页"""
    # 疑似重复图片报告
    st.markdown("### 🚨 疑似重复图片报告")
    
    # 控制选项
    st.markdown("#### ⚙️ 显示设置")
    col1, col2, col3 = st.columns(3)
    with col1:
        dup_threshold = st.slider(
            "疑似重复阈值",
            min_value=0,
            max_value=20,
            value=config["distance_thresholds"]["very_similar"],
            help="汉明距离小于此值的图片将被视为疑似重复"
        )
    with col2:
        groups_per_row = st.slider(
            "每行显示组数",
            min_value=1,
            max_value=4,
            value=2,
            help="控制一行显示多少对疑似重复图片"
        )
    with col3:
        image_width = st.slider(
            "图片显示宽度",
            min_value=80,
            max_value=200,
            value=120,
            step=10,
            help="调整图片的显示大小"
        )
    
    duplicates = create_duplicate_report(st.session_state.results, dup_threshold)
    
    # 显示总体统计
    total_duplicates = sum(len(size_duplicates) for size_duplicates in duplicates.values())
    if total_duplicates > 0:
        st.success(f"🎯 共发现 **{total_duplicates}** 对疑似重复图片")
    else:
        st.info("✨ 未发现疑似重复图片")
    
    render_duplicate_groups(duplicates, groups_per_row, image_width)

def render_duplicate_groups(duplicates, groups_per_row, image_width):
    """渲染疑似重复图片组"""
    for size, size_duplicates in duplicates.items():
        with st.expander(f"📋 哈希尺寸 {size} - 发现 {len(size_duplicates)} 对疑似重复", expanded=len(size_duplicates) > 0):
            if size_duplicates:
                # 按行显示重复图片对
                for row_start in range(0, len(size_duplicates), groups_per_row):
                    row_pairs = size_duplicates[row_start:row_start + groups_per_row]
                    
                    # 创建列布局
                    cols = st.columns(groups_per_row)
                    
                    for col_idx, pair in enumerate(row_pairs):
                        with cols[col_idx]:
                            render_duplicate_pair(pair, row_start + col_idx + 1, image_width)
                    
                    # 如果这一行没有填满，为空列添加占位符
                    for empty_col_idx in range(len(row_pairs), groups_per_row):
                        with cols[empty_col_idx]:
                            st.empty()
            else:
                st.info("未发现疑似重复的图片")

def render_duplicate_pair(pair, pair_index, image_width):
    """渲染单个疑似重复图片对"""
    img1_path = Path(pair["image1"])
    img2_path = Path(pair["image2"])
    
    # 获取图片信息
    img1_info = get_image_info(img1_path)
    img2_info = get_image_info(img2_path)
    
    # 使用容器包装每一对图片
    with st.container():
        # 自定义样式的头部
        st.markdown(f'<div class="duplicate-header">疑似重复 {pair_index}</div>', unsafe_allow_html=True)
        st.markdown(f"**汉明距离:** {pair['distance']} | **相似度:** {100-pair['distance']*2:.1f}%")
        
        # 图片1
        if img1_path.exists():
            st.image(str(img1_path), caption=f"📸 {img1_path.name}", width=image_width)
        st.caption(f"📁 {img1_path.parent.name}")
        if img1_info:
            st.caption(f"📏 {img1_info['dimensions']} | 💾 {img1_info['size_str']}")
        
        # 分隔符
        st.markdown('<div class="vs-separator">⚡ VS ⚡</div>', unsafe_allow_html=True)
        
        # 图片2
        if img2_path.exists():
            st.image(str(img2_path), caption=f"📸 {img2_path.name}", width=image_width)
        st.caption(f"📁 {img2_path.parent.name}")
        if img2_info:
            st.caption(f"📏 {img2_info['dimensions']} | 💾 {img2_info['size_str']}")
        
        # 文件大小比较
        render_file_size_comparison(img1_path, img2_path, img1_info, img2_info)
        
        # 添加分隔线
        st.markdown("---")

def render_file_size_comparison(img1_path, img2_path, img1_info, img2_info):
    """渲染文件大小比较"""
    if img1_info and img2_info:
        size1 = img1_info['size']
        size2 = img2_info['size']
        if size1 < size2:
            st.success("🟢 较小文件")
        elif size1 > size2:
            st.error("🔴 较大文件")
        else:
            st.info("🟡 大小相同")
    elif img1_path.exists() and img2_path.exists():
        # 备用方案：直接读取文件大小
        size1 = img1_path.stat().st_size
        size2 = img2_path.stat().st_size
        if size1 < size2:
            st.success("🟢 较小文件")
        elif size1 > size2:
            st.error("🔴 较大文件")
        else:
            st.info("🟡 大小相同")

def render_export_tab():
    """渲染导出下载标签页"""
    # 导出和下载
    st.markdown("### 📥 导出和下载")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### JSON 格式")
        json_data = {
            "timestamp": datetime.now().isoformat(),
            "total_images": len(st.session_state.image_files),
            "image_files": [str(f) for f in st.session_state.image_files],
            "results": st.session_state.results
        }
        
        st.download_button(
            label="📥 下载 JSON 报告",
            data=json.dumps(json_data, ensure_ascii=False, indent=2),
            file_name=f"phash_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    with col2:
        st.markdown("#### Excel 格式")
        excel_data = export_results_excel(st.session_state.results, st.session_state.image_files)
        
        st.download_button(
            label="📥 下载 Excel 报告",
            data=excel_data,
            file_name=f"phash_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    st.markdown("#### 📊 报告包含内容")
    st.info("""
    - **总体统计**: 各哈希尺寸的性能对比
    - **详细对比**: 所有图片对的汉明距离
    - **疑似重复**: 高相似度图片识别
    - **可视化图表**: 距离分布和性能对比
    """)

def render_analysis_results(config):
    """渲染分析结果"""
    st.markdown("## 📈 分析结果")
    
    # 添加标签页
    tab1, tab2, tab3, tab4 = st.tabs(["📊 总体分析", "🔍 详细对比", "🚨 疑似重复", "📥 导出下载"])
    
    with tab1:
        render_overall_analysis_tab()
    
    with tab2:
        render_detailed_comparison_tab(config)
    
    with tab3:
        render_duplicate_detection_tab(config)
    
    with tab4:
        render_export_tab()

def render_welcome_page():
    """渲染欢迎页面"""
    st.markdown("""
    ## 👋 欢迎使用 pHash 图片相似度分析工具
    
    ### 🚀 功能特点
    - **多尺寸分析**: 支持同时分析多个哈希尺寸
    - **交互式界面**: 美观的 Streamlit 界面，支持实时进度显示
    - **结果可视化**: 丰富的图表和统计信息
    - **数据持久化**: 结果保存为 JSON 格式，可重复加载
    - **智能过滤**: 按汉明距离过滤相似图片
    - **图片预览**: 直观的图片对比展示
    
    ### 📋 使用说明
    1. 在左侧选择"新建分析"或"加载已有结果"
    2. 输入图片文件夹路径
    3. 选择要分析的哈希尺寸
    4. 点击"开始分析"按钮
    5. 查看分析结果和统计信息
    
    ### 💡 提示
    - 哈希尺寸越大，计算时间越长，但精度更高
    - 汉明距离越小，图片越相似
    - 建议先用较小的尺寸进行快速测试
    """)

def main():
    config = load_config()
    app_config = config["app_config"]
    
    load_session_state()
    
    # 标题
    st.markdown(f'<h1 class="main-header">{app_config["icon"]} {app_config["title"]}</h1>', unsafe_allow_html=True)
    
    mode = render_sidebar(config)
    
    if mode == "新建分析":        # 文件夹选择
        image_folder, selected_sizes, similarity_threshold, export_format = render_new_analysis_sidebar(config)
        
        handle_new_analysis(config, image_folder, selected_sizes, export_format)
    
    else:  # 加载已有结果
        handle_load_results()

    # 显示结果
    if st.session_state.analysis_complete and st.session_state.results:
        render_analysis_results(config)
    elif not st.session_state.analysis_complete:
        render_welcome_page()

if __name__ == "__main__":
    main()
