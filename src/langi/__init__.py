"""langi 包：基于外部 OCR 服务(Umi OCR)的图片主要语言识别工具。

公开 API:
    detect_image_language(path, client=None) -> dict
    batch_detect(paths, client=None, rename=True, suffix_map=None, output_json=None) -> list

可扩展：通过在 LanguageHeuristics.LANGUAGE_PRIORITY 中增加新语言优先级，并在
heuristics 中添加对应检测逻辑（基于字符集合或自定义规则）。
"""
from .client import CommandUmiOCRClient, HttpUmiOCRClient
from .detector import detect_image_language, batch_detect, LanguageHeuristics

__all__ = [
    "CommandUmiOCRClient",
    "HttpUmiOCRClient",
    "detect_image_language",
    "batch_detect",
    "LanguageHeuristics",
]
