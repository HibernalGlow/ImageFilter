"""
测试虚拟文件夹嵌套问题的测试用例
"""
import os
import tempfile
import shutil
from pathlib import Path

VIRTUAL_FOLDER_SUFFIX = '.folderzip'

def test_resolve_virtual_path_bug():
    """测试 _resolve_virtual_path 函数的 bug"""
    
    # 当前有问题的实现
    def _resolve_virtual_path_buggy(path: str):
        if path.endswith(VIRTUAL_FOLDER_SUFFIX):
            return os.path.dirname(path), True  # BUG: 应该是去掉后缀，不是取父目录
        return path, False
    
    # 修复后的实现
    def _resolve_virtual_path_fixed(path: str):
        if path.endswith(VIRTUAL_FOLDER_SUFFIX):
            # 去掉 .folderzip 后缀得到真实目录路径
            real_path = path[:-len(VIRTUAL_FOLDER_SUFFIX)]
            return real_path, True
        return path, False
    
    # 测试用例
    test_cases = [
        "folder1.folderzip",
        "path/to/folder2.folderzip",
        "deep/nested/path/folder3.folderzip",
    ]
    
    print("=" * 80)
    print("虚拟文件夹路径解析测试")
    print("=" * 80)
    
    for test_path in test_cases:
        buggy_result, _ = _resolve_virtual_path_buggy(test_path)
        fixed_result, _ = _resolve_virtual_path_fixed(test_path)
        
        print(f"\n输入路径: {test_path}")
        print(f"  有 bug 的结果: {buggy_result}")
        print(f"  修复后的结果: {fixed_result}")
        print(f"  预期目录名: {test_path.replace(VIRTUAL_FOLDER_SUFFIX, '')}")
        
        if buggy_result != fixed_result:
            print(f"  [WARNING] BUG发现! 有问题的实现返回了错误的路径")

def simulate_nested_move_bug():
    """模拟反复移动导致嵌套的场景"""
    
    print("\n" + "=" * 80)
    print("模拟虚拟文件夹反复移动嵌套问题")
    print("=" * 80)
    
    # 创建临时测试目录
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        
        # 创建测试目录结构
        # 假设有一个文件夹 "漫画A" 被当作虚拟压缩包
        manga_dir = base_dir / "漫画A"
        manga_dir.mkdir()
        
        # 在里面放一些图片（模拟）
        (manga_dir / "page1.jpg").touch()
        (manga_dir / "page2.jpg").touch()
        
        print(f"\n初始结构:")
        print(f"  {tmpdir}/")
        print(f"    漫画A/")
        print(f"      page1.jpg")
        print(f"      page2.jpg")
        
        # 模拟第一次处理：rawfilter 将 "漫画A" 识别为虚拟压缩包
        # 伪文件路径应该是: "漫画A.folderzip"
        virtual_file_path = "漫画A.folderzip"
        
        # 有 bug 的解析
        def buggy_resolve(path):
            if path.endswith(VIRTUAL_FOLDER_SUFFIX):
                return os.path.dirname(path), True
            return path, False
        
        # 假设要移动到 multi 目录
        multi_dir = base_dir / "multi"
        multi_dir.mkdir()
        
        print(f"\n第一次移动（使用有 bug 的逻辑）:")
        buggy_src, _ = buggy_resolve(virtual_file_path)
        print(f"  虚拟文件: {virtual_file_path}")
        print(f"  解析出的源路径: '{buggy_src}' (空字符串表示当前目录)")
        print(f"  目标路径: multi/")
        print(f"  [BUG] os.path.dirname('漫画A.folderzip') 返回空字符串!")
        print(f"  [BUG] 这会导致移动整个当前目录或出错!")
        
        # 正确的解析
        def fixed_resolve(path):
            if path.endswith(VIRTUAL_FOLDER_SUFFIX):
                return path[:-len(VIRTUAL_FOLDER_SUFFIX)], True
            return path, False
        
        print(f"\n第一次移动（使用修复后的逻辑）:")
        fixed_src, _ = fixed_resolve(virtual_file_path)
        print(f"  虚拟文件: {virtual_file_path}")
        print(f"  解析出的源路径: {fixed_src}")
        print(f"  目标路径: multi/{fixed_src}")
        print(f"  [OK] 正确: 会将 '漫画A' 目录移动到 'multi/漫画A'")
        
        # 模拟嵌套场景
        print(f"\n" + "-" * 80)
        print("模拟嵌套问题场景：")
        print("-" * 80)
        
        # 假设有嵌套路径的虚拟文件
        nested_virtual = "subdir/漫画B.folderzip"
        
        buggy_nested_src, _ = buggy_resolve(nested_virtual)
        fixed_nested_src, _ = fixed_resolve(nested_virtual)
        
        print(f"\n嵌套路径的虚拟文件: {nested_virtual}")
        print(f"  有 bug 的解析: '{buggy_nested_src}'")
        print(f"  修复后的解析: '{fixed_nested_src}'")
        print(f"  预期: 'subdir/漫画B'")
        
        if buggy_nested_src == "subdir":
            print(f"  [BUG] 会移动整个 'subdir' 目录而不是 'subdir/漫画B'")
            print(f"  [BUG] 导致: 下次扫描时 'subdir' 下的其他内容也会被重复处理")

def test_actual_move_scenario():
    """测试实际的移动场景"""
    
    print("\n" + "=" * 80)
    print("实际移动场景测试")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        
        # 创建测试结构
        manga1 = base_dir / "漫画A汉化版"
        manga1.mkdir()
        (manga1 / "page1.jpg").touch()
        
        manga2 = base_dir / "漫画A原版"  
        manga2.mkdir()
        (manga2 / "page1.jpg").touch()
        
        print(f"\n初始结构:")
        for item in base_dir.rglob("*"):
            rel_path = item.relative_to(base_dir)
            indent = "  " * (len(rel_path.parts) - 1)
            marker = "[DIR]" if item.is_dir() else "[FILE]"
            print(f"  {indent}{marker} {item.name}")
        
        # 模拟 rawfilter 处理
        # 两个虚拟文件: "漫画A汉化版.folderzip", "漫画A原版.folderzip"
        # 它们会被分到同一组，假设要把原版移到 trash
        
        print(f"\n处理逻辑:")
        print(f"  1. 发现虚拟文件: '漫画A汉化版.folderzip' 和 '漫画A原版.folderzip'")
        print(f"  2. 分组: 两者属于同一组（漫画A）")
        print(f"  3. 决策: 保留汉化版，将原版移到 trash")
        
        # Bug 场景
        virtual_to_move = "漫画A原版.folderzip"
        buggy_src = os.path.dirname(virtual_to_move)  # 返回 ""
        
        print(f"\n有 Bug 的移动:")
        print(f"  源: '{buggy_src}' (空字符串)")
        print(f"  目标: trash/漫画A原版")
        print(f"  [BUG] 问题: 无法正确定位源目录!")
        
        # 修复后
        fixed_src = virtual_to_move[:-len(VIRTUAL_FOLDER_SUFFIX)]  # "漫画A原版"
        
        print(f"\n修复后的移动:")
        print(f"  源: {fixed_src}")
        print(f"  目标: trash/{fixed_src}")
        print(f"  [OK] 正确定位到 '漫画A原版' 目录")
        
        # 实际执行移动（修复后的逻辑）
        trash_dir = base_dir / "trash"
        trash_dir.mkdir()
        
        src_path = base_dir / fixed_src
        dst_path = trash_dir / fixed_src
        
        if src_path.exists():
            shutil.move(str(src_path), str(dst_path))
            print(f"\n移动后的结构:")
            for item in base_dir.rglob("*"):
                rel_path = item.relative_to(base_dir)
                indent = "  " * (len(rel_path.parts) - 1)
                marker = "[DIR]" if item.is_dir() else "[FILE]"
                print(f"  {indent}{marker} {item.name}")

if __name__ == "__main__":
    test_resolve_virtual_path_bug()
    simulate_nested_move_bug()
    test_actual_move_scenario()
    
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print("\n问题根源:")
    print("  _resolve_virtual_path 函数使用了 os.path.dirname() 而不是去掉后缀")
    print("  这导致虚拟文件路径被错误解析")
    print("\n修复方案:")
    print("  将 os.path.dirname(path) 改为 path[:-len(VIRTUAL_FOLDER_SUFFIX)]")
    print("  或使用 os.path.splitext(path)[0]")
    print("\n" + "=" * 80)

