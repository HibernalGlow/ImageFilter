"""可选的库级语言检测封装。

优先使用:
 1. pycld3  (Google Compact Language Detector v3)  -> pip install pycld3
 2. langdetect (Port of Google's language-detection) -> pip install langdetect

返回标准化: chinese / japanese / english / unknown
内部还可区分简繁, 通过 opencc 估算 (主项目已依赖 opencc-python-reimplemented)。
"""
from __future__ import annotations
from typing import Optional

try:  # pycld3
    import pycld3  # type: ignore
except Exception:  # noqa: BLE001
    pycld3 = None  # type: ignore

try:  # langdetect
    from langdetect import detect as _ld_detect  # type: ignore
except Exception:  # noqa: BLE001
    _ld_detect = None  # type: ignore

try:
    from opencc import OpenCC  # type: ignore
except Exception:  # noqa: BLE001
    OpenCC = None  # type: ignore

_cc_t2s = OpenCC('t2s') if OpenCC else None

def _is_traditional(text: str) -> bool:
    if not _cc_t2s or not text:
        return False
    converted = _cc_t2s.convert(text)
    diff = sum(a != b for a, b in zip(text, converted))
    return diff > 0 and diff / max(len(text), 1) > 0.05

def detect_language_lib(text: str) -> Optional[str]:
    """使用外部库尝试检测语言, 未识别返回 None.

    仅映射 zh -> chinese, ja -> japanese, en -> english.
    其它返回 None 让上层回退到正则启发式。
    """
    if not text or len(text.strip()) < 2:
        return None

    if pycld3 is not None:
        try:
            res = pycld3.get_language(text)
            if res and res.is_reliable:
                code = res.language
                if code.startswith('zh'):
                    return 'chinese'
                if code == 'ja':
                    return 'japanese'
                if code == 'en':
                    return 'english'
        except Exception:  # noqa: BLE001
            pass

    if _ld_detect is not None:
        try:
            code = _ld_detect(text)
            if code.startswith('zh'):
                return 'chinese'
            if code == 'ja':
                return 'japanese'
            if code == 'en':
                return 'english'
        except Exception:  # noqa: BLE001
            pass

    return None

__all__ = ["detect_language_lib", "_is_traditional"]
