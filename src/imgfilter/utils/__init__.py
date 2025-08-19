"""
ImgFilter 图片检测器集合

提供各种专用的图片检测器，可独立使用。
"""

from imgfilter.detectors.watermark import WatermarkDetector
from imgfilter.detectors.text import CVTextImageDetector
from imgfilter.detectors.duplicate import DuplicateImageDetector
from imgfilter.detectors.small import SmallImageDetector
from imgfilter.detectors.gray.grayscale import GrayscaleImageDetector

__all__ = [
    "WatermarkDetector",
    "CVTextImageDetector",
    "DuplicateImageDetector",
    "SmallImageDetector",
    "GrayscaleImageDetector",
]