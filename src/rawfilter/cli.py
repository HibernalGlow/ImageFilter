import argparse
from .run import process_directory, ReportGenerator
from .utils import process_paths, get_paths_from_clipboard
from loguru import logger
import sys

def setup_cli_parser():
    parser = argparse.ArgumentParser(description='处理重复压缩包文件')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--clipboard', action='store_true', help='从剪贴板读取路径')
    group.add_argument('-p', '--paths', nargs='+', help='要处理的目录路径')
    parser.add_argument('-s', '--sample-count', type=int, default=3, help='每个压缩包抽取的图片样本数量（默认3）')
    parser.add_argument('--create-shortcuts', action='store_true', help='创建快捷方式而不是移动文件')
    parser.add_argument('--enable-multi-main', action='store_true', help='为每个multi组创建主文件副本')
    parser.add_argument('--name-only-mode', action='store_true', help='仅名称模式：仅通过文件名判断，不检查内部文件数量和清晰度，不添加{}标记')
    parser.add_argument('--report', type=str, help='指定报告文件名（默认为"处理报告_时间戳.md"）')
    return parser

def run_application(args):
    paths = []
    if hasattr(args, 'clipboard') and args.clipboard:
        paths.extend(get_paths_from_clipboard())
    elif hasattr(args, 'paths') and args.paths:
        if isinstance(args.paths, str):
            paths.extend([p.strip() for p in args.paths.split(',') if p.strip()])
        else:
            paths.extend(args.paths)
    else:
        print("请输入要处理的路径（每行一个，输入空行结束）：")
        while True:
            try:
                line = input().strip()
                if not line:
                    break
                paths.append(line)
            except EOFError:
                break
            except KeyboardInterrupt:
                print("用户取消输入")
    if not paths:
        logger.info("[#error_log] ❌ 未提供任何路径")
        return False
    valid_paths = process_paths(paths)
    if not valid_paths:
        logger.info("[#error_log] ❌ 没有有效的路径可处理")
        return False
    report_generator = ReportGenerator()
    for path in valid_paths:
        logger.info("[#process] 🚀 开始处理目录: %s", path)
        process_directory(
            path,
            report_generator,
            create_shortcuts=args.create_shortcuts if hasattr(args, 'create_shortcuts') else False,
            enable_multi_main=args.enable_multi_main if hasattr(args, 'enable_multi_main') else False,
            name_only_mode=args.name_only_mode if hasattr(args, 'name_only_mode') else False
        )
        logger.info("[#process] ✨ 目录处理完成: %s", path)
        if hasattr(args, 'report') and args.report:
            report_path = report_generator.save_report(path, args.report)
        else:
            report_path = report_generator.save_report(path)
        if report_path:
            logger.info("[#process] 📝 报告已保存到: %s", report_path)
        else:
            logger.info("[#error_log] ❌ 保存报告失败")
    return True

def main():
    parser = setup_cli_parser()
    preset_configs = {
        "基本模式": {
            "description": "从剪贴板读取路径，执行标准处理",
            "checkbox_options": ["--clipboard"],
            "input_values": {}
        },
        "仅名称模式": {
            "description": "仅通过文件名判断，不检查内部文件，不添加{}标记",
            "checkbox_options": ["--clipboard", "--name-only-mode"],
            "input_values": {}
        },
        "快捷方式模式": {
            "description": "创建快捷方式而不是移动文件",
            "checkbox_options": ["--clipboard", "--create-shortcuts"],
            "input_values": {}
        },
        "多文件保留模式": {
            "description": "为每个multi组创建主文件副本",
            "checkbox_options": ["--clipboard", "--enable-multi-main"],
            "input_values": {}
        },
        "完整模式": {
            "description": "启用所有高级功能",
            "checkbox_options": ["--clipboard", "--create-shortcuts", "--enable-multi-main"],
            "input_values": {
                "--sample-count": "5"
            }
        }
    }
    has_args = len(sys.argv) > 1
    if has_args:
        args = parser.parse_args(sys.argv[1:])
        run_application(args)
    else:
        # 使用 lata cli 启动 taskfile 界面
        try:
            import subprocess
            from pathlib import Path

            # 获取当前包目录（rawfilter 目录）
            script_dir = Path(__file__).parent

            # 启动 lata cli
            result = subprocess.run(
                "lata",
                cwd=script_dir
            )

            return result.returncode

        except Exception as e:
            print(f"启动 lata cli 失败: {e}")
            print("请通过命令行参数运行。")
            return 1
