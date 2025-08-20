import os
from typing import List, Dict, Tuple, Callable

__all__ = ["prune_uncensored_chinese", "is_uncensored_version"]

# 常见无修正关键词（中/日/英常见写法，可继续补充）
UNCENSORED_KEYWORDS = [
    "无修", "無修", "uncensor", "無碼", "无码", "無穢"
]


def is_uncensored_version(path_or_name: str) -> bool:
    name = os.path.basename(path_or_name).lower()
    for kw in UNCENSORED_KEYWORDS:
        if kw.lower() in name:
            return True
    return False


def prune_uncensored_chinese(
    chinese_versions: List[str],
    base_dir: str,
    trash_dir: str,
    result_stats: Dict[str, int],
    safe_move_file: Callable[[str, str], bool],
    logger,
    create_shortcuts: bool = False,
    create_shortcut: Callable[[str, str], bool] | None = None,
) -> List[str]:
    """在已有版本裁剪后，对多个汉化版本再按无修正优先策略处理。

    逻辑:
      - 若中文版本数量 <=1 或不存在任何无修正版本 => 不处理。
      - 若存在 >=1 个无修正版本:
          * 若仅 1 个无修正: 保留该文件, 其余汉化版本全部丢入 trash。
          * 若多个无修正: 仅保留所有无修正版本进入后续 multi 逻辑; 其它汉化版本全部丢入 trash。
    返回更新后的 chinese_versions 列表。
    """
    if len(chinese_versions) <= 1:
        return chinese_versions

    uncensored = [f for f in chinese_versions if is_uncensored_version(f)]
    if not uncensored:
        return chinese_versions  # 没有无修正, 不做额外处理

    # 需要丢弃的汉化版本（有修正）
    to_trash = [f for f in chinese_versions if f not in uncensored]

    if len(uncensored) == 1:
        # 单一无修正, 丢弃其余
        keep = set(uncensored)
        for rel_path in to_trash:
            src_path = os.path.join(base_dir, rel_path)
            dst_path = os.path.join(trash_dir, os.path.relpath(src_path, base_dir))
            if create_shortcuts and create_shortcut is not None:
                shortcut_path = os.path.splitext(dst_path)[0]
                if create_shortcut(src_path, shortcut_path):
                    logger.info("[#file_ops] ✅ 已创建快捷方式(有修正 -> trash): {}", rel_path)
                    result_stats['created_shortcuts'] = result_stats.get('created_shortcuts', 0) + 1
            else:
                if safe_move_file(src_path, dst_path):
                    logger.info("[#file_ops] 🗑️ 无修正优先: 已移动有修正版到trash: {}", rel_path)
                    result_stats['moved_to_trash'] = result_stats.get('moved_to_trash', 0) + 1
        return list(keep)
    else:
        # 多个无修正 -> 丢弃所有有修正, 保留所有无修正给后续 multi 逻辑
        for rel_path in to_trash:
            src_path = os.path.join(base_dir, rel_path)
            dst_path = os.path.join(trash_dir, os.path.relpath(src_path, base_dir))
            if create_shortcuts and create_shortcut is not None:
                shortcut_path = os.path.splitext(dst_path)[0]
                if create_shortcut(src_path, shortcut_path):
                    logger.info("[#file_ops] ✅ 已创建快捷方式(有修正 -> trash): {}", rel_path)
                    result_stats['created_shortcuts'] = result_stats.get('created_shortcuts', 0) + 1
            else:
                if safe_move_file(src_path, dst_path):
                    logger.info("[#file_ops] 🗑️ 无修正优先: 已移动有修正版到trash: {}", rel_path)
                    result_stats['moved_to_trash'] = result_stats.get('moved_to_trash', 0) + 1
        return uncensored
