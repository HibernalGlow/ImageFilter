from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    # 中文匹配：基本区、扩展A、兼容表意、以及高位扩展(B~F常用范围子集)
    CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002A6DF]")
    # 假名 (日文特有脚本)：平假名 + 片假名
    JAPANESE_KANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
    ENGLISH_RE = re.compile(r"[A-Za-z]")
    # 日文常见标点/符号/全角装饰
    JP_PUNCT_RE = re.compile(r"[「」『』【】〈〉《》〔〕（）。？！…～・ー＝：；＋＊★☆※→⇒◎◇◆△▽▼▲○●❖■□“”]")
    # 高频功能词/语尾 (粗糙匹配，只做提示，避免过拟合；不做严格分词)
    JP_PARTICLE_RE = re.compile(r"(の|です|ます|でした|ません|して|した|してい|してる|ない|たい|だった|から|けど|けれど|ても|もの|こと|よう|では|には|には|には|には|って)")

    # 默认阈值，可被 CLI 覆盖
    MIN_TOTAL_CHARS: int = 5       # 去除空白后最少总字符
    MIN_LANG_CHARS: int = 3        # 目标语言最少字符
    MIN_LANG_PROPORTION: float = 0.5  # 目标语言在全部字符中最小占比

    @classmethod
    def configure(cls, min_total: int | None = None, min_lang: int | None = None, min_prop: float | None = None):
        if min_total is not None:
            cls.MIN_TOTAL_CHARS = max(1, min_total)
        if min_lang is not None:
            cls.MIN_LANG_CHARS = max(1, min_lang)
        if min_prop is not None:
            cls.MIN_LANG_PROPORTION = max(0.0, min(1.0, min_prop))

    @classmethod
    def detect(cls, text: str) -> str:
        if not text.strip():
            return "unknown"
        lib_lang = detect_language_lib(text)
        if lib_lang:
            return lib_lang
        compact = re.sub(r"\s+", "", text)
        if len(compact) < cls.MIN_TOTAL_CHARS:
            return "unknown"
        c = len(cls.CHINESE_RE.findall(compact))  # 汉字 (中日公用 + 中专用)
        kana = len(cls.JAPANESE_KANA_RE.findall(compact))  # 假名
        e = len(cls.ENGLISH_RE.findall(compact))
        if c == kana == e == 0:
            return "unknown"

        # 日文特征评分：假名 + 标点 + 语法功能词
        jp_punct = len(cls.JP_PUNCT_RE.findall(compact))
        jp_particles = len(cls.JP_PARTICLE_RE.findall(compact))
        # 计算一个简单分数：假名数 *1 + 标点*2 + 功能词*4
        jp_score = kana + jp_punct * 2 + jp_particles * 4
        kana_ratio = kana / max(c + kana, 1)

        # 判定为日文的条件（任一满足即可）：
        # 1) 假名占 (汉字+假名) 比例 >= 3% 且 假名 >=2
        # 2) 假名 >=1 且 日文特征分 >= 6
        # 3) 功能词 >=2
        japanese_likely = (
            (kana >= 2 and kana_ratio >= 0.03) or
            (kana >= 1 and jp_score >= 6) or
            (jp_particles >= 2)
        )

        # 若疑似日文且假名存在，则优先判为日文（即使汉字多，日文文本常以汉字为主，假名辅助）
        if japanese_likely and kana >= 1:
            winner = "japanese"
            w_count = kana  # 使用假名计数做阈值校验
        else:
            # 中文偏向策略：假名较少或无假名时，如果汉字占 (汉字+英字) >=30% 且 >= 英文，则视为中文
            if c > 0 and (c / max(c + e, 1)) >= 0.30 and c >= e:
                winner = "chinese"
                w_count = c
            else:
                # 传统三语言竞争：把假名视为日文的主体字符数
                counts = {"chinese": c, "japanese": kana, "english": e}
                max_count = max(counts.values())
                candidates = [k for k, v in counts.items() if v == max_count and v > 0]
                if len(candidates) == 1:
                    winner = candidates[0]
                else:
                    if c > 0 and any(k != "chinese" for k in candidates) and c >= 0.9 * max_count:
                        winner = "chinese"
                    else:
                        winner = max(candidates, key=lambda x: cls.LANGUAGE_PRIORITY.get(x, 0))
                w_count = counts.get(winner, 0)

        if w_count < cls.MIN_LANG_CHARS:
            return "unknown"
        if (w_count / len(compact)) < cls.MIN_LANG_PROPORTION:
            return "unknown"
        return winner


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
    workers: int | None = None,
) -> List[Dict]:
    if client is None:
        client = CommandUmiOCRClient()
    suffix_map = {**DEFAULT_SUFFIX_MAP, **(suffix_map or {})}
    results: List[Dict] = [None] * len(paths)  # type: ignore
    total = len(paths)

    def _task(index_path: Tuple[int, str | Path]):
        idx, p = index_path
        info = detect_image_language(p, client)
        if rename and not info.get("error"):
            suffix = suffix_map.get(info["language"], suffix_map["unknown"])
            new_path = _rename_with_suffix(Path(info["path"]), suffix)
            info["renamed_path"] = str(new_path)
        return idx, info

    if workers is None or workers <= 1:
        for idx, p in enumerate(paths, 1):
            if progress:
                try:
                    progress(idx, total, str(p))
                except Exception:  # noqa: BLE001
                    pass
            _, info = _task((idx - 1, p))
            results[idx - 1] = info
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(_task, (i, p)): i for i, p in enumerate(paths)}
            done_count = 0
            for fut in as_completed(future_map):
                i, info = fut.result()
                results[i] = info
                done_count += 1
                if progress:
                    try:
                        progress(done_count, total, str(paths[i]))
                    except Exception:  # noqa: BLE001
                        pass
    if output_json:
        try:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            logger.error(f"写出 JSON 失败 {output_json}: {e}")
    return results  # type: ignore
