import os
import logging
from typing import List, Dict, Tuple, Set, Union
from PIL import Image
import pillow_avif  # AVIF支持
import pillow_jxl 
from io import BytesIO
from loguru import logger
os.environ["HF_DATASETS_OFFLINE"] = "1"  
os.environ["TRANSFORMERS_OFFLINE"] = "1"
# os.environ["HF_HOME"] = "/path/to/your/permanent/cache"
from imgutils.validate import get_monochrome_score, is_monochrome  

class GrayscaleImageDetector:
    """灰度图、黑白图和纯色图检测器"""
    
    def __init__(self):
        """初始化灰度图检测器"""
        # 直接使用is_monochrome函数替代GrayscaleDetector
        pass
        
    def detect_grayscale_images(self, image_files: List[str]) -> Tuple[Set[str], Dict[str, Dict]]:
        """
        检测灰度图、纯白图和纯黑图
        
        Args:
            image_files: 图片文件列表
            
        Returns:
            Tuple[Set[str], Dict[str, Dict]]: (要删除的文件集合, 删除原因字典)
        """
        to_delete = set()
        removal_reasons = {}
        
        for img_path in image_files:
            try:
                with open(img_path, 'rb') as f:
                    img_data = f.read()
                    
                result, reason = self.detect_grayscale_image_bytes(img_data)
                
                if reason in ['monochrome', 'pure_white', 'pure_black', 'white_image']:
                    to_delete.add(img_path)
                    
                    # 映射原因到详细信息
                    details_map = {
                        'monochrome': '灰度图片',
                        'pure_white': '纯白图片',
                        'pure_black': '纯黑图片',
                        'white_image': '白图片'
                    }
                    
                    removal_reasons[img_path] = {
                        'reason': reason,
                        'details': details_map.get(reason, '黑白图片')
                    }
                    
                    logger.info(f"[#file_ops]🖼️ 标记删除{removal_reasons[img_path]['details']}: {os.path.basename(img_path)}")
                    
            except Exception as e:                logger.error(f"[#file_ops]❌ 处理灰度图检测失败 {img_path}: {e}")

                
        return to_delete, removal_reasons
        
    def detect_grayscale_image_bytes(self, image_data):
        """
        检测图片字节数据是否为灰度图/纯白图/纯黑图
        
        Args:
            image_data: PIL.Image对象或图片字节数据
            
        Returns:
            Tuple[Union[bytes, None], Union[str, None]]: (处理后的图片数据, 错误原因)
        """
        try:
            # 先确保是PIL Image对象
            if isinstance(image_data, Image.Image):
                img = image_data
            else:
                img = Image.open(BytesIO(image_data))
                
            # 先计算灰度分数
            mono_score = get_monochrome_score(img)
            logger.info(f"[#file_ops]🖼️ 灰度分数: {mono_score:.4f}")
            
            # 根据灰度分数判断是否为灰度图
            if mono_score >= 0.85:  # 可以根据需要调整阈值
                logger.info(f"[#file_ops]🖼️ 基于灰度分数 {mono_score:.4f} 检测到灰度图")
                return (None, 'monochrome')
                
            # 使用is_monochrome函数进行辅助判断
            if is_monochrome(img):
                logger.info(f"[#file_ops]🖼️ is_monochrome检测到灰度图")
                return (None, 'monochrome')
                
            # 进一步尝试使用传统方法检测
            if isinstance(image_data, Image.Image):
                img = image_data
            else:
                img = Image.open(BytesIO(image_data))
            
            # 传统方法检测
            result, reason = self._legacy_detect_grayscale(img)
            if reason:
                return result, reason
                
            # 未检测到灰度图，返回原始数据
            if isinstance(image_data, Image.Image):
                return image_data, None
            else:
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format=img.format or 'PNG')
                return img_byte_arr.getvalue(), None
                
        except ValueError as ve:
            logger.info(f"[#file_ops]❌ 灰度检测发生ValueError: {str(ve)}")
            return (None, 'grayscale_detection_error')
        except Exception as e:
            logger.info(f"[#file_ops]❌ 灰度检测发生错误: {str(e)}")
            return None, 'grayscale_detection_error'
            
    def _legacy_detect_grayscale(self, img):
        """传统方法检测灰度图（作为备用）"""
        try:
            # 转换为RGB模式
            if img.mode not in ["RGB", "RGBA", "L"]:
                img = img.convert("RGB")
            
            # 1. 检查是否为原始灰度图
            if img.mode == "L":
                logger.info("[#file_ops]🖼️ 检测到原始灰度图")
                return None, 'monochrome'
            
            # 2. 获取图片的采样点进行分析
            width, height = img.size
            sample_points = [
                (x, y) 
                for x in range(0, width, max(1, width//10))
                for y in range(0, height, max(1, height//10))
            ][:100]  # 最多取100个采样点
            
            # 获取采样点的像素值
            pixels = [img.getpixel(point) for point in sample_points]
            
            # 3. 检查是否为纯白图
            if all(all(v > 240 for v in (pixel if isinstance(pixel, tuple) else (pixel,))) 
                   for pixel in pixels):
                logger.info("[#file_ops]🖼️ 检测到纯白图")
                return None, 'pure_white'
            
            # 4. 检查是否为纯黑图
            if all(all(v < 15 for v in (pixel if isinstance(pixel, tuple) else (pixel,))) 
                   for pixel in pixels):
                logger.info("[#file_ops]🖼️ 检测到纯黑图")
                return None, 'pure_black'
            
            # 5. 检查是否为灰度图
            if img.mode in ["RGB", "RGBA"]:
                is_grayscale = all(
                    abs(pixel[0] - pixel[1]) < 5 and 
                    abs(pixel[1] - pixel[2]) < 5 and
                    abs(pixel[0] - pixel[2]) < 5 
                    for pixel in pixels
                )
                if is_grayscale:
                    logger.info("[#file_ops]🖼️ 检测到灰度图(RGB接近)")
                    return None, 'monochrome'
                    
            return img, None
        except Exception as e:
            logger.error(f"[#file_ops]❌ 传统灰度检测发生错误: {str(e)}")
            return img, None
            
            
if __name__ == "__main__":
    import sys
    import argparse
    from pathlib import Path
    import datetime
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='灰度图片检测工具')
    parser.add_argument('--path', type=str, help='要检测的图片路径或包含图片的文件夹路径')
    parser.add_argument('--recursive', action='store_true', help='是否递归处理子文件夹')
    parser.add_argument('--delete', action='store_true', help='是否删除检测到的灰度图')
    parser.add_argument('--report', action='store_true', help='生成Markdown报告', default=True)
    args = parser.parse_args()
    
    # 如果没有提供路径，则提示用户输入
    if not args.path:
        args.path = input("请输入图片路径或文件夹路径: ").strip()
        if not args.path:
            print("未提供有效路径，退出程序")
            sys.exit(1)
    
    # 获取所有图片文件
    path = Path(args.path)
    if path.is_file():
        image_files = [str(path)]
    else:
        # 支持的图片格式
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.avif', '.jxl']
        
        if args.recursive:
            # 递归获取所有图片
            image_files = []
            for ext in image_extensions:
                image_files.extend([str(f) for f in path.glob(f'**/*{ext}')])
        else:
            # 只获取当前文件夹下的图片
            image_files = []
            for ext in image_extensions:
                image_files.extend([str(f) for f in path.glob(f'*{ext}')])
    
    # 检查是否找到图片
    if not image_files:
        print(f"在指定路径 '{args.path}' 下未找到图片文件")
        sys.exit(1)
    
    print(f"发现 {len(image_files)} 个图片文件，开始检测...")
    
    # 创建灰度图检测器并开始检测
    detector = GrayscaleImageDetector()
    to_delete, reasons = detector.detect_grayscale_images(image_files)
    
    # 输出检测结果
    print(f"\n检测完成！发现 {len(to_delete)} 个灰度/纯色图片:")
    
    # 按照类型分类输出
    reason_groups = {}
    for img_path, info in reasons.items():
        reason = info['reason']
        if reason not in reason_groups:
            reason_groups[reason] = []
        reason_groups[reason].append(img_path)
    
    # 输出分类结果
    for reason, paths in reason_groups.items():
        detail = paths[0] and reasons[paths[0]]['details']
        print(f"\n{detail} ({len(paths)}个):")
        for path in paths:
            print(f" - {path}")
      # 生成Markdown报告
    if args.report and reason_groups:
        # 创建报告文件名，使用当前时间
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_name = f"grayscale_report_{now}.md"
        
        # 保存原始路径对象，防止被覆盖
        input_path = Path(args.path)
        # 如果路径是目录，则在该目录下创建报告，否则在当前目录创建
        report_dir = input_path if input_path.is_dir() else input_path.parent
        report_path = report_dir / report_name
        
        print(f"\n正在生成Markdown报告: {report_path}")
        
        with open(report_path, "w", encoding="utf-8") as f:
            # 写入报告标题和摘要
            f.write(f"# 灰度图片检测报告\n\n")
            f.write(f"**检测时间**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**检测路径**: {args.path}\n\n")
            f.write(f"**递归检测**: {'是' if args.recursive else '否'}\n\n")
            f.write(f"**检测结果摘要**:\n\n")
            f.write(f"- 检测的图片总数: {len(image_files)}\n")
            f.write(f"- 发现灰度/纯色图片: {len(to_delete)}\n\n")
            
            # 按类型分组写入检测到的图片
            f.write(f"## 检测结果详情\n\n")
            
            for reason, paths in reason_groups.items():
                detail = reasons[paths[0]]['details']
                f.write(f"### {detail} ({len(paths)}个)\n\n")
                
                # 创建表格头部
                f.write("| 图片 | 文件路径 |\n")
                f.write("|------|----------|\n")
                
                # 添加每个图片的预览和路径
                for img_path in paths:
                    # 使用绝对路径以确保在Markdown中正确显示
                    abs_path = os.path.abspath(img_path).replace("\\", "/")
                    filename = os.path.basename(img_path)
                    f.write(f"| ![]({abs_path}) | {filename} |\n")
                
                f.write("\n")
            
            # 添加注意事项
            f.write("## 注意事项\n\n")
            f.write("1. 图片预览在Markdown查看器中可能需要调整图片路径\n")
            f.write("2. 若要删除检测到的图片，请使用 `--delete` 参数重新运行命令\n")
            
        print(f"Markdown报告已生成: {report_path}")
    
    # 如果指定了删除选项，则删除灰度图
    if args.delete and to_delete:
        confirm = input(f"\n确认要删除这 {len(to_delete)} 个图片吗? (y/n): ").strip().lower()
        if confirm == 'y':
            for img_path in to_delete:
                try:
                    os.remove(img_path)
                    print(f"已删除: {img_path}")
                except Exception as e:
                    print(f"删除失败 {img_path}: {e}")
            print(f"\n删除操作完成，共删除 {len(to_delete)} 个文件")
        else:
            print("已取消删除操作")
