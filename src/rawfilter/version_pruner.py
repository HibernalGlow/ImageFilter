import os, re
from typing import List, Dict, Tuple

__all__ = ["prune_version_files"]

_version_pattern = re.compile(r'(?:[\s_\-\(\[])?v(\d+)(?=[)\]]?$|$)', re.IGNORECASE)


def _extract_version(stem: str) -> int | None:
    m = _version_pattern.search(stem)
    if m:
        try:
            return int(m.group(1))
        except ValueError:  # pragma: no cover - 防御
            return None
    return None


def _strip_version(stem: str) -> str:
    return re.sub(r'[\s_\-\(\[]v\d+[)\]]?$', '', stem, flags=re.IGNORECASE).rstrip()


def prune_version_files(
    chinese_versions: List[str],
    other_versions: List[str],
    base_dir: str,
    trash_dir: str,
    result_stats: Dict[str, int],
    safe_move_file,
    logger,
) -> Tuple[List[str], List[str]]:
    """裁剪多版本文件, 只保留最高版本 (无版本视为 v1)。

    规则:
      1. 同一目录下, 去掉末尾 vN 标记后(含可选括号/空格/下划/短横)若基名相同且出现 >=v2, 则触发裁剪。
      2. 无版本号视作 v1。
      3. 选最大版本; 若同最大版本有多个文件, 选文件大小最大的保留。
      4. 其余全部移入 trash, 计入 moved_to_trash。

    返回更新后的 (chinese_versions, other_versions)。
    """
    all_files = chinese_versions + other_versions
    if not all_files:
        return chinese_versions, other_versions

    base_map: Dict[str, List[str]] = {}
    for rel_path in all_files:
        file_name = os.path.basename(rel_path)
        stem, ext = os.path.splitext(file_name)
        base_key = _strip_version(stem).lower() + ext.lower()
        base_map.setdefault(base_key, []).append(rel_path)

    low_version_to_trash: List[str] = []
    for _base_key, files_list in base_map.items():
        if len(files_list) <= 1:
            continue
        version_info = []  # (version, rel_path)
        has_hi_ver = False
        for rel_path in files_list:
            stem, _ = os.path.splitext(os.path.basename(rel_path))
            ver = _extract_version(stem) or 1
            if ver >= 2:
                has_hi_ver = True
            version_info.append((ver, rel_path))
        if not has_hi_ver:
            continue
        max_ver = max(v for v, _ in version_info)
        max_candidates = [p for v, p in version_info if v == max_ver]
        if len(max_candidates) == 1:
            keep_file = max_candidates[0]
        else:
            keep_file = max(max_candidates, key=lambda p: os.path.getsize(os.path.join(base_dir, p)))
        for v, p in version_info:
            if p != keep_file:
                low_version_to_trash.append(p)

    for rel_path in low_version_to_trash:
        src_path = os.path.join(base_dir, rel_path)
        dst_path = os.path.join(trash_dir, os.path.relpath(src_path, base_dir))
        if safe_move_file(src_path, dst_path):
            logger.info("[#file_ops] 🗑️ 版本裁剪: 已移动低版本到trash: {}", rel_path)
            result_stats['moved_to_trash'] = result_stats.get('moved_to_trash', 0) + 1
            if rel_path in chinese_versions:
                chinese_versions.remove(rel_path)
            if rel_path in other_versions:
                other_versions.remove(rel_path)

    return chinese_versions, other_versions
