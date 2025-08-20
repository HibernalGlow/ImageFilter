import os
import re
from typing import List, Dict, Tuple, Callable, Any

# 默认无修正关键字，可扩展
DEFAULT_UNCENSORED_KEYWORDS = [
    "无修正", "無修正", "無修", "uncensored", "無碼", "无码", "無穢", "無修正版"
]

# 默认DL关键字
DEFAULT_DL_KEYWORDS = ["dl", "dl版", "DL", "DL版"]

_version_pattern = re.compile(r'(?:[\s_\-\(\[])?v(\d+)(?=[)\]]?$|$)', re.IGNORECASE)


def _extract_version(stem: str) -> int | None:
    m = _version_pattern.search(stem)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def _strip_version(stem: str) -> str:
    return re.sub(r'[\s_\-\(\[]v\d+[)\]]?$', '', stem, flags=re.IGNORECASE).rstrip()


def _group_by_base(files: List[str]) -> Dict[str, List[str]]:
    base_map: Dict[str, List[str]] = {}
    for rel_path in files:
        file_name = os.path.basename(rel_path)
        stem, ext = os.path.splitext(file_name)
        base_key = _strip_version(stem).lower() + ext.lower()
        base_map.setdefault(base_key, []).append(rel_path)
    return base_map


def apply_prune_rules(
    chinese_versions: List[str],
    other_versions: List[str],
    base_dir: str,
    trash_dir: str,
    result_stats: Dict[str, int],
    safe_move_file: Callable[[str, str], bool],
    logger,
    create_shortcuts: bool = False,
    create_shortcut: Callable[[str, str], bool] | None = None,
    rules: List[Dict[str, Any]] | None = None,
) -> Tuple[List[str], List[str]]:
    """根据一组规则依次裁剪文件。规则是一个字典列表，支持两种type：

    - type: 'version'  -> 按 vN 版本号保留最大版本（无版本视为 v1），与先前 version_pruner 等价。
    - type: 'keyword'  -> 按关键词匹配裁剪。字段：
        - keywords: List[str]
        - scope: 'chinese'|'other'|'both'
        - keep_matching: bool  (True: 保留匹配项；False: 丢弃匹配项)

    规则按列表顺序应用，先应用的规则会移除文件，后续规则基于更新后的集合再执行。

    返回更新后的 (chinese_versions, other_versions)
    """
    # 默认规则顺序：版本号 -> 无修正(优先保留匹配) -> DL(丢弃DL)
    if rules is None:
        rules = [
            {"type": "version"},
            {"type": "keyword", "keywords": DEFAULT_UNCENSORED_KEYWORDS, "scope": "chinese", "keep_matching": True},
            {"type": "keyword", "keywords": DEFAULT_DL_KEYWORDS, "scope": "chinese", "keep_matching": False},
        ]

    # 合并两类用于某些规则的处理
    for rule in rules:
        try:
            rtype = rule.get('type')
            if rtype == 'version':
                # 版本规则作用于所有文件（原逻辑）
                all_files = chinese_versions + other_versions
                if not all_files:
                    continue
                base_map = _group_by_base(all_files)
                to_trash: List[str] = []
                for _k, files_list in base_map.items():
                    if len(files_list) <= 1:
                        continue
                    version_info: List[tuple[int, str]] = []
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
                            to_trash.append(p)
                for rel_path in to_trash:
                    src = os.path.join(base_dir, rel_path)
                    dst = os.path.join(trash_dir, os.path.relpath(src, base_dir))
                    if safe_move_file(src, dst):
                        logger.info("[#file_ops] 🗑️ 版本裁剪: 已移动低版本到trash: {}", rel_path)
                        result_stats['moved_to_trash'] = result_stats.get('moved_to_trash', 0) + 1
                        if rel_path in chinese_versions:
                            chinese_versions.remove(rel_path)
                        if rel_path in other_versions:
                            other_versions.remove(rel_path)

            elif rtype == 'keyword':
                keywords = [k.lower() for k in rule.get('keywords', [])]
                scope = rule.get('scope', 'both')
                keep_matching = bool(rule.get('keep_matching', True))

                # Build target list
                targets = []
                if scope in ('chinese', 'both'):
                    targets.extend([(p, 'chinese') for p in chinese_versions])
                if scope in ('other', 'both'):
                    targets.extend([(p, 'other') for p in other_versions])

                if not targets:
                    continue

                # 匹配项
                matched = [p for p, _ in targets if any(kw in os.path.basename(p).lower() for kw in keywords)]
                if not matched:
                    continue

                # 根据 keep_matching 决定保留或丢弃匹配项
                if keep_matching:
                    # 保留匹配项；若匹配项数量为1，则丢弃目标集合中的其余项；若>1，则丢弃目标集合中不匹配的项，保留所有匹配项
                    if len(matched) == 1:
                        # 丢弃目标集合中非匹配的所有
                        to_trash = [p for p, _ in targets if p not in matched]
                    else:
                        to_trash = [p for p, _ in targets if p not in matched]
                else:
                    # 丢弃匹配项
                    to_trash = matched

                # 执行移动并从列表中移除
                for rel_path in to_trash:
                    src = os.path.join(base_dir, rel_path)
                    dst = os.path.join(trash_dir, os.path.relpath(src, base_dir))
                    if create_shortcuts and create_shortcut is not None:
                        shortcut_path = os.path.splitext(dst)[0]
                        if create_shortcut(src, shortcut_path):
                            logger.info("[#file_ops] ✅ 已创建快捷方式(关键词裁剪 -> trash): {}", rel_path)
                            result_stats['created_shortcuts'] = result_stats.get('created_shortcuts', 0) + 1
                            # 继续移除列表
                            if rel_path in chinese_versions:
                                chinese_versions.remove(rel_path)
                            if rel_path in other_versions:
                                other_versions.remove(rel_path)
                            continue
                    if safe_move_file(src, dst):
                        logger.info("[#file_ops] 🗑️ 关键词裁剪: 已移动到trash: {}", rel_path)
                        result_stats['moved_to_trash'] = result_stats.get('moved_to_trash', 0) + 1
                        if rel_path in chinese_versions:
                            chinese_versions.remove(rel_path)
                        if rel_path in other_versions:
                            other_versions.remove(rel_path)

            else:
                logger.debug(f"未知的裁剪规则类型: {rtype}")
        except Exception as e:
            logger.error(f"[#error_log] 裁剪规则执行异常 {rule}: {e}")

    return chinese_versions, other_versions
