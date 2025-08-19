import numpy as np
from PIL import Image
from dataclasses import dataclass, field
from typing import Union, Tuple, Optional
from io import BytesIO
import pillow_avif
import pillow_jxl
from rich.console import Console
from rich.table import Table
from rich.style import Style
from loguru import logger
from glob import glob
import os
import argparse

@dataclass
class GrayscaleConfig:
    """黑白图片检测的配置类"""
    white_threshold: int = 240      # 白色像素的阈值
    white_score_threshold: float = 0.9 # 调整为更合理的阈值
    black_threshold: int = 20       # 黑色像素的阈值
    grayscale_std_threshold: int = 800  # 大幅提高标准差阈值，适应实际图片情况
    grayscale_score_threshold: float = 0.85  # 降低灰度得分要求
    color_ratio_threshold: float = 0.2 # 允许的彩色像素比例
    remove_config: dict = field(default_factory=lambda: {
        'grayscale': True,    # 删除所有灰度图
        'white': True,        # 删除普通白图
        'pure_white': True,   # 删除纯白图
        'pure_black': True    # 删除纯黑图
    })

    # 增强默认配置校验
    def __post_init__(self):
        if not 0 <= self.white_score_threshold <= 1:
            raise ValueError("白图得分阈值必须在0-1之间")
        if self.grayscale_std_threshold < 0:
            raise ValueError("灰度标准差阈值不能为负数")

@dataclass
class GrayscaleResult:
    """黑白图片检测的结果类"""
    def __init__(self, 
                 is_grayscale: bool,
                 is_white_image: bool,
                 is_pure_white: bool,
                 is_pure_black: bool,
                 channel_std: float,
                 grayscale_score: float,
                 white_score: float,
                 black_score: float,
                #  colorful_score: float,
                 config: GrayscaleConfig):
        self.is_grayscale = is_grayscale
        self.is_white_image = is_white_image
        self.is_pure_white = is_pure_white
        self.is_pure_black = is_pure_black
        self.channel_std = channel_std
        self.grayscale_score = grayscale_score
        self.white_score = white_score
        self.black_score = black_score
        # self.colorful_score = colorful_score
        if not isinstance(config, GrayscaleConfig):
            raise TypeError("config必须是GrayscaleConfig实例")
        self.config = config

    @property
    def removal_reason(self) -> Optional[str]:
        """带防御性编程的删除原因判断"""
        try:
            if not hasattr(self, 'config') or self.config is None:
                return None
                
            reasons = []
            conf = self.config.remove_config
            
            # 添加阈值范围校验
            if conf.get('pure_white', False) and self.is_pure_white:
                if self.white_score >= self.config.white_score_threshold:
                    reasons.append("pure_white")
                    
            if conf.get('pure_black', False) and self.is_pure_black:
                if self.black_score >= self.config.black_threshold:
                    reasons.append("pure_black")
                    
            if conf.get('white', False) and self.is_white_image:
                reasons.append("white")
                
            if conf.get('grayscale', False) and self.is_grayscale:
                reasons.append("grayscale")
                
            return "|".join(reasons) if reasons else None
            
        except Exception as e:
            logger.error(f"[#update_log]❌ removal_reason计算错误: {str(e)}")
            return None

class GrayscaleDetector:
    """黑白图片检测器"""
    def __init__(self, config: GrayscaleConfig = None):
        self.config = config or GrayscaleConfig()
        if not isinstance(self.config, GrayscaleConfig):
            raise ValueError("无效的配置类型")

    def calculate_colorfulness(self, image: Image.Image) -> float:
        """独立计算图片鲜艳度（基于饱和度）"""
        if image.mode != 'HSV':
            hsv_img = image.convert('HSV')
        else:
            hsv_img = image
        s_channel = np.array(hsv_img.getchannel('S'))/255.0
        return np.mean(s_channel)

    def analyze_image(self, image: Union[str, Image.Image, bytes]) -> GrayscaleResult:
        """分析图片是否为黑白图/白图
        
        Args:
            image: 可以是图片路径、PIL Image对象或图片字节数据
            
        Returns:
            GrayscaleResult: 包含检测结果的对象
        """
        try:
            # 确保我们有一个PIL Image对象
            if isinstance(image, str):
                img = Image.open(image)
            elif isinstance(image, bytes):
                img = Image.open(BytesIO(image))
            elif isinstance(image, Image.Image):
                img = image
            else:
                raise ValueError("不支持的图片输入类型")

            # 转换图片为RGB模式（去除Alpha通道）
            if img.mode in ('RGBA', 'LA'):
                img = img.convert('RGB')
                
            # 转换为numpy数组进行处理
            image_np = np.array(img)
            
            # 优先判断灰度模式
            if img.mode == 'L':
                return GrayscaleResult(
                    is_grayscale=True,
                    is_white_image=False,
                    is_pure_white=False,
                    is_pure_black=False,
                    channel_std=0.0,
                    grayscale_score=1.0,
                    white_score=0.0,
                    black_score=0.0,
                    # colorful_score=0.0,
                    config=self.config
                )

            # 改进的灰度判断逻辑
            if len(image_np.shape) == 3:
                # 计算RGB通道的标准差
                channel_std = np.std(image_np.var(axis=2))
                
                # 计算RGB通道的差异
                r, g, b = image_np[:,:,0], image_np[:,:,1], image_np[:,:,2]
                max_diff = np.maximum(np.abs(r-g), np.maximum(np.abs(g-b), np.abs(b-r)))
                color_ratio = np.mean(max_diff > 30)  # 通道差异大于30的像素比例
                
                is_grayscale = (channel_std <= self.config.grayscale_std_threshold and 
                               color_ratio <= self.config.color_ratio_threshold)
            else:
                channel_std = 0.0
                is_grayscale = True
            
            # 计算白色得分
            gray_image = img.convert('L')
            gray_np = np.array(gray_image)
            total_pixels = gray_np.size
            
            # 纯白图检测
            is_pure_white = np.all(gray_np >= self.config.white_threshold)
            white_pixels = np.sum(gray_np >= self.config.white_threshold)
            white_score = white_pixels / total_pixels
            
            # 纯黑图检测
            is_pure_black = np.all(gray_np <= self.config.black_threshold)
            black_pixels = np.sum(gray_np <= self.config.black_threshold)
            
            # 综合灰度得分
            grayscale_score = (white_score + (black_pixels / total_pixels)) / 2

            # 独立计算鲜艳度（按需调用）
            # colorful_score = self.calculate_colorfulness(img) if len(image_np.shape) == 3 else 0.0

            # 性能优化：缩放大图
            if max(img.size) > 2000:
                img = img.resize((img.width//2, img.height//2), Image.Resampling.LANCZOS)

            return GrayscaleResult(
                is_grayscale=is_grayscale,
                is_white_image=white_score >= self.config.white_score_threshold,
                is_pure_white=is_pure_white,
                is_pure_black=is_pure_black,
                channel_std=channel_std,
                grayscale_score=grayscale_score,
                white_score=white_score,
                black_score=black_pixels / total_pixels,
                # colorful_score=self.calculate_colorfulness(img) if len(image_np.shape) == 3 else 0.0,
                config=self.config
            )
            
        except Exception as e:
            logger.error(f"图片分析失败: {str(e)}", exc_info=True)
            raise ValueError(f"分析失败: {str(e)}") from e

    def is_white_image(self, image: Union[str, Image.Image, bytes]) -> bool:
        """快速检查是否为白图
        
        Args:
            image: 可以是图片路径、PIL Image对象或图片字节数据
            
        Returns:
            bool: 是否为白图
        """
        result = self.analyze_image(image)
        return result.is_white_image 

# 修改测试代码部分
if __name__ == "__main__":
    def test_detector(image_dir: str):
        """使用rich表格显示检测结果"""
        detector = GrayscaleDetector()
        console = Console()
        image_files = glob(os.path.join(image_dir, "*.*"))
        supported_formats = ['.jpg', '.jpeg', '.jxl', '.png', '.bmp', '.webp', '.tiff', '.gif', '.avif']
        
        # 创建带样式的表格
        table = Table(title="📷 黑白图片检测结果", show_header=True, header_style="bold cyan")
        table.add_column("文件名", width=18, style="magenta")
        table.add_column("尺寸", width=10)
        table.add_column("灰度图", justify="center", width=6)
        table.add_column("白图", justify="center", width=6)
        table.add_column("纯白", justify="center", width=6)
        table.add_column("纯黑", justify="center", width=6)
        table.add_column("白分", justify="right", width=6)
        table.add_column("灰分", justify="right", width=6)
        table.add_column("标准差", justify="right", width=8)
        
        results = []
        for img_path in image_files:
            ext = os.path.splitext(img_path)[1].lower()
            if ext not in supported_formats:
                continue
                
            try:
                with Image.open(img_path) as img:
                    result = detector.analyze_image(img)
                    # 根据结果添加不同颜色样式
                    style = Style(
                        color="green" if result.is_grayscale else "yellow",
                        bold=result.is_pure_white or result.is_pure_black
                    )
                    table.add_row(
                        os.path.basename(img_path),
                        "x".join(map(str, img.size)),
                        "✅" if result.is_grayscale else "❌",
                        "✅" if result.is_white_image else "❌",
                        "🔥" if result.is_pure_white else "─",
                        "⚫" if result.is_pure_black else "─",
                        f"{result.white_score:.2f}",
                        f"{result.grayscale_score:.2f}",
                        f"{result.channel_std:.1f}",
                        style=style
                    )
                    results.append(result)
            except Exception as e:
                table.add_row(
                    os.path.basename(img_path),
                    "ERROR",
                    "⛔", "⛔", "⛔", "⛔",
                    style=Style(color="red", bold=True)
                )
        
        console.print(table)
        
        # 在表格输出部分添加统计信息
        total = len(image_files)
        grayscale_count = sum(1 for r in results if r.is_grayscale)
        white_count = sum(1 for r in results if r.is_white_image)
        console.print(f"\n[bold]统计结果：[/bold] 共{total}张 | 灰度图{grayscale_count}张 | 白图{white_count}张")
    
    parser = argparse.ArgumentParser(description='黑白图检测测试（使用rich表格输出）')
    parser.add_argument('--dir', type=str, 
                       default=os.path.join(os.path.dirname(__file__), 'test'), 
                       help='要测试的图片目录')
    parser.add_argument('--white', type=float, default=0.95, help='白图阈值 (0-1)')
    parser.add_argument('--std', type=int, default=3, help='灰度标准差阈值')
    args = parser.parse_args()
    
    if os.path.isdir(args.dir):
        test_detector(args.dir)
    else:
        print(f"[bold red]错误：[/bold red] 目录 {args.dir} 不存在")