from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, Optional
from loguru import logger

from .client import CommandUmiOCRClient, OCRResult
from .langlib import detect_language_lib

# 语言后缀映射默认值
DEFAULT_SUFFIX_MAP = {
    "chinese": "_zh",
    "english": "_en",
    "japanese": "_ja",
    "unknown": "_unk",
}

@dataclass
class LanguageStats:
    lang: str
    char_count: int

class LanguageHeuristics:
    """基于字符类别的简单语言判定，可扩展。"""

    # 各语言优先级 (越大优先级越高)，用于混合文本时的 tie-breaker
    LANGUAGE_PRIORITY: Dict[str, int] = {
        "chinese": 3,
        "english": 2,
        "japanese": 1,
        "unknown": 0,
    }

    # 扩展中文匹配：基本区、扩展A、兼容表意、以及高位扩展(B~F常用范围子集)
    CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002A6DF]")
    JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf]")
    ENGLISH_RE = re.compile(r"[A-Za-z]")

    @classmethod
    def detect(cls, text: str) -> str:
        if not text.strip():
            return "unknown"
        lib_lang = detect_language_lib(text)
        if lib_lang:
            return lib_lang
        c = len(cls.CHINESE_RE.findall(text))
        j = len(cls.JAPANESE_RE.findall(text))
        e = len(cls.ENGLISH_RE.findall(text))
        if c == j == e == 0:
            return "unknown"

        # 若存在中文字符，且中文字符占 (中+英) 的比例 >= 0.3，则直接视为中文，避免繁体字 + 少量英文字母被误判
        if c > 0 and (c / max(c + e, 1)) >= 0.30 and c >= e:
            return "chinese"

        counts = {"chinese": c, "japanese": j, "english": e}
        max_count = max(counts.values())
        candidates = [k for k, v in counts.items() if v == max_count and v > 0]
        if len(candidates) == 1:
            return candidates[0]
        # 并列 -> 若包含中文且中文数量接近最大(>=90%最大值)也偏向中文
        if c > 0 and any(k != "chinese" for k in candidates) and c >= 0.9 * max_count:
            return "chinese"
        return max(candidates, key=lambda x: cls.LANGUAGE_PRIORITY.get(x, 0))


def _aggregate_text(results: Sequence[OCRResult]) -> str:
    return " ".join(r.text for r in results if r.text)


def detect_image_language(path: str | Path, client: CommandUmiOCRClient | None = None) -> Dict:
    p = Path(path)
    if client is None:
        client = CommandUmiOCRClient()
    try:
        ocr_results = client.ocr_image(p)
    except Exception as e:  # noqa: BLE001
        logger.error(f"OCR 失败 {p}: {e}")
        return {"path": str(p), "language": "unknown", "text": "", "error": str(e)}
    text = _aggregate_text(ocr_results)
    lang = LanguageHeuristics.detect(text)
    return {
        "path": str(p),
        "language": lang,
        "text": text,
        "text_length": len(text.strip()),
    }


def _rename_with_suffix(p: Path, suffix: str) -> Path:
    if not suffix:
        return p
    stem = p.stem
    if stem.endswith(suffix):
        return p
    new_name = f"{stem}{suffix}{p.suffix}" if p.suffix else f"{stem}{suffix}"
    new_path = p.with_name(new_name)
    try:
        p.rename(new_path)
        return new_path
    except Exception as e:  # noqa: BLE001
        logger.warning(f"重命名失败 {p} -> {new_path}: {e}")
        return p


def batch_detect(
    paths: Sequence[str | Path],
    client: CommandUmiOCRClient | None = None,
    rename: bool = True,
    suffix_map: Dict[str, str] | None = None,
    output_json: str | None = None,
    progress: callable | None = None,
) -> List[Dict]:
    if client is None:
        client = CommandUmiOCRClient()
    suffix_map = {**DEFAULT_SUFFIX_MAP, **(suffix_map or {})}
    results: List[Dict] = []
    total = len(paths)
    for idx, p in enumerate(paths, 1):
        if progress:
            try:
                progress(idx, total, str(p))
            except Exception:  # noqa: BLE001
                pass
        info = detect_image_language(p, client)
        if rename and not info.get("error"):
            suffix = suffix_map.get(info["language"], suffix_map["unknown"])
            new_path = _rename_with_suffix(Path(info["path"]), suffix)
            info["renamed_path"] = str(new_path)
        results.append(info)
    if output_json:
        try:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            logger.error(f"写出 JSON 失败 {output_json}: {e}")
    return results
