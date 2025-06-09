"""配置模块，包含预设和配置管理"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from rich.console import Console
from rich.prompt import Prompt, Confirm

# 控制台对象
console = Console()

# 默认预设配置文件路径（改为同目录）
DEFAULT_CONFIG_PATH = Path(__file__).parent / "presets.json"

# 默认预设
DEFAULT_PRESETS = {
    "默认": {
        "description": "默认配置 - 小于等于1800像素宽度",
        "source_dir": "E:\\999EHV",
        "target_dir": "E:\\7EHV",
        "dimension_rules": [
            {
                "min_width": 0,
                "max_width": 1800,
                "min_height": -1,
                "max_height": -1,
                "mode": "and",
                "folder": ""
            }
        ],
        "cut_mode": False,
        "max_workers": 16,
        "threshold_count": 3
    },
    "双重分组": {
        "description": "双重分组 - 按不同宽度范围分组",
        "source_dir": "E:\\999EHV",
        "target_dir": "E:\\7EHV",
        "dimension_rules": [
            {
                "min_width": 0,
                "max_width": 900,
                "min_height": -1,
                "max_height": -1,
                "mode": "and",
                "folder": "900px"
            },
            {
                "min_width": 901,
                "max_width": 1800,
                "min_height": -1,
                "max_height": -1,
                "mode": "and",
                "folder": "1800px"
            }
        ],
        "cut_mode": False,
        "max_workers": 16,
        "threshold_count": 3
    },
    "宽高双重匹配": {
        "description": "宽高双重匹配 - 同时考虑宽度和高度",
        "source_dir": "E:\\999EHV",
        "target_dir": "E:\\Dimension",
        "dimension_rules": [
            {
                "min_width": 0,
                "max_width": 900,
                "min_height": 0,
                "max_height": 600,
                "mode": "and",
                "folder": "小图"
            },
            {
                "min_width": 901,
                "max_width": 1800,
                "min_height": 601,
                "max_height": 1200,
                "mode": "and",
                "folder": "中等"
            },
            {
                "min_width": 1801,
                "max_width": -1,
                "min_height": 1201,
                "max_height": -1,
                "mode": "and",
                "folder": "高清"
            }
        ],
        "cut_mode": False,
        "max_workers": 16,
        "threshold_count": 3
    }
} 

def load_presets() -> Dict[str, Any]:
    """加载预设配置"""
    if not DEFAULT_CONFIG_PATH.exists():
        # 创建默认配置文件
        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 写入默认预设
        with open(DEFAULT_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_PRESETS, f, ensure_ascii=False, indent=4)
        return DEFAULT_PRESETS
    
    try:
        with open(DEFAULT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            presets = json.load(f)
        # 兼容旧版本配置（width_ranges -> dimension_rules）
        for preset_name, preset in presets.items():
            if 'width_ranges' in preset and 'dimension_rules' not in preset:
                # 转换旧配置到新格式
                preset['dimension_rules'] = []
                for range_info in preset['width_ranges']:
                    preset['dimension_rules'].append({
                        'min_width': range_info['min'],
                        'max_width': range_info['max'],
                        'min_height': -1,
                        'max_height': -1,
                        'mode': 'or',
                        'folder': range_info.get('folder', '')
                    })
                del preset['width_ranges']
        return presets
    except Exception as e:
        from loguru import logger
        logger.error(f"加载预设失败: {str(e)}")
        return DEFAULT_PRESETS

def print_presets(presets: Dict[str, Any]) -> None:
    """打印所有预设"""
    console.print("\n[bold cyan]===== 可用预设 =====")
    for i, (name, preset) in enumerate(presets.items(), 1):
        console.print(f"[bold green]{i}.[/] [yellow]{name}[/] - {preset['description']}")
        
        # 打印尺寸规则
        for j, rule in enumerate(preset['dimension_rules'], 1):
            min_width = rule["min_width"]
            max_width = "不限" if rule["max_width"] == -1 else rule["max_width"]
            
            min_height = "不限" if rule["min_height"] == -1 else rule["min_height"]
            max_height = "不限" if rule["max_height"] == -1 else rule["max_height"]
            
            folder = rule["folder"] or "根目录"
            mode = "AND" if rule["mode"] == "and" else "OR"
            
            width_info = f"宽: {min_width}-{max_width}px"
            height_info = f"高: {min_height}-{max_height}px"
            console.print(f"   [dim]范围 {j}: {width_info} {mode} {height_info} -> {folder}[/]")
            
        console.print(f"   [dim]源目录: {preset['source_dir']}[/]")
        console.print(f"   [dim]目标目录: {preset['target_dir']}[/]")
        console.print(f"   [dim]操作模式: {'移动' if preset['cut_mode'] else '复制'}, "
                    f"匹配阈值: {preset['threshold_count']}, "
                    f"并行线程: {preset['max_workers']}[/]")
        console.print()

def select_preset(presets: Dict[str, Any]) -> tuple:
    """交互式选择预设"""
    print_presets(presets)
    
    preset_names = list(presets.keys())
    try:
        choice = Prompt.ask(
            "[bold cyan]请选择预设[/]", 
            choices=[str(i) for i in range(1, len(preset_names) + 1)],
            default="1"
        )
        selected_name = preset_names[int(choice) - 1]
        return selected_name, presets[selected_name]
    except (ValueError, IndexError) as e:
        console.print(f"[bold red]选择错误: {str(e)}[/]")
        return preset_names[0], presets[preset_names[0]]

def manage_presets(presets: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """管理预设（简化版 - 只允许选择预设）"""
    console.print("\n[bold cyan]===== 预设管理 =====")
    console.print("[bold green]1.[/] 使用现有预设")
    console.print("[bold green]2.[/] 使用命令行参数")
    console.print("[bold yellow]注: 预设编辑功能已移除，请直接修改同目录下的presets.json文件[/]")
    
    action = Prompt.ask("[bold]请选择操作", choices=["1", "2"], default="1")
    
    if action == "1":
        # 使用现有预设
        preset_name, preset = select_preset(presets)
        return preset
    else:
        # 使用命令行参数，返回None表示使用命令行参数
        return None 