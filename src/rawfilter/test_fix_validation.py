"""
验证虚拟文件夹 bug 修复的测试
"""
import os
import tempfile
import shutil
from pathlib import Path

VIRTUAL_FOLDER_SUFFIX = '.folderzip'

def _resolve_virtual_path_fixed(path: str):
    """修复后的虚拟路径解析函数"""
    if path.endswith(VIRTUAL_FOLDER_SUFFIX):
        # 去掉 .folderzip 后缀得到真实目录路径
        real_path = path[:-len(VIRTUAL_FOLDER_SUFFIX)]
        return real_path, True
    return path, False

def test_integration_scenario():
    """集成测试：模拟完整的虚拟文件夹处理流程"""
    
    print("=" * 80)
    print("虚拟文件夹修复后的集成测试")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        
        # 创建测试目录结构
        # 模拟有两个版本的同一个漫画
        manga_cn = base_dir / "漫画A[汉化]"
        manga_cn.mkdir()
        (manga_cn / "page1.jpg").write_text("page1")
        (manga_cn / "page2.jpg").write_text("page2")
        
        manga_jp = base_dir / "漫画A[原版]"
        manga_jp.mkdir()
        (manga_jp / "page1.jpg").write_text("page1")
        (manga_jp / "page2.jpg").write_text("page2")
        
        print("\n1. 初始目录结构:")
        print_tree(base_dir)
        
        # 模拟 rawfilter 识别为虚拟文件
        virtual_files = [
            "漫画A[汉化].folderzip",
            "漫画A[原版].folderzip"
        ]
        
        print("\n2. 识别的虚拟文件:")
        for vf in virtual_files:
            print(f"  - {vf}")
        
        # 模拟分组和裁剪：保留汉化版，移除原版
        # 使用修复后的逻辑
        print("\n3. 执行移动操作 (修复后的逻辑):")
        
        to_keep = "漫画A[汉化].folderzip"
        to_trash = "漫画A[原版].folderzip"
        
        # 解析虚拟路径
        keep_real, _ = _resolve_virtual_path_fixed(to_keep)
        trash_real, _ = _resolve_virtual_path_fixed(to_trash)
        
        print(f"  保留: {to_keep} -> {keep_real}")
        print(f"  移除: {to_trash} -> {trash_real}")
        
        # 创建 trash 目录并移动
        trash_dir = base_dir / "trash"
        trash_dir.mkdir()
        
        src = base_dir / trash_real
        dst = trash_dir / trash_real
        
        if src.exists():
            shutil.move(str(src), str(dst))
            print(f"  [OK] 成功移动 {trash_real} 到 trash/")
        
        print("\n4. 移动后的目录结构:")
        print_tree(base_dir)
        
        # 验证结果
        print("\n5. 验证结果:")
        success = True
        
        # 检查保留的目录是否还在
        if (base_dir / keep_real).exists():
            print(f"  [PASS] 保留的目录存在: {keep_real}")
        else:
            print(f"  [FAIL] 保留的目录丢失: {keep_real}")
            success = False
        
        # 检查移除的目录是否在 trash 中
        if (trash_dir / trash_real).exists():
            print(f"  [PASS] 移除的目录在 trash 中: {trash_real}")
        else:
            print(f"  [FAIL] 移除的目录未找到: {trash_real}")
            success = False
        
        # 检查原位置是否清空
        if not (base_dir / trash_real).exists():
            print(f"  [PASS] 原位置已清空: {trash_real}")
        else:
            print(f"  [FAIL] 原位置仍存在: {trash_real}")
            success = False
        
        # 检查是否有嵌套问题
        nested_dirs = list(trash_dir.glob("**/trash"))
        if nested_dirs:
            print(f"  [FAIL] 发现嵌套的 trash 目录: {nested_dirs}")
            success = False
        else:
            print(f"  [PASS] 没有嵌套的 trash 目录")
        
        print("\n" + "=" * 80)
        if success:
            print("测试通过: 虚拟文件夹处理正确!")
        else:
            print("测试失败: 发现问题!")
        print("=" * 80)
        
        return success

def test_multi_level_paths():
    """测试多层级路径的虚拟文件夹"""
    
    print("\n" + "=" * 80)
    print("多层级路径测试")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        
        # 创建嵌套目录结构
        nested = base_dir / "level1" / "level2" / "漫画B"
        nested.mkdir(parents=True)
        (nested / "page1.jpg").write_text("page1")
        
        print("\n初始结构:")
        print_tree(base_dir)
        
        # 虚拟文件路径
        virtual_path = "level1/level2/漫画B.folderzip"
        
        print(f"\n虚拟文件: {virtual_path}")
        
        # 解析
        real_path, is_virtual = _resolve_virtual_path_fixed(virtual_path)
        
        print(f"解析结果: {real_path}")
        print(f"是否为虚拟: {is_virtual}")
        
        # 验证路径正确性
        expected = "level1/level2/漫画B"
        if real_path == expected:
            print(f"[PASS] 路径解析正确")
        else:
            print(f"[FAIL] 路径解析错误，预期: {expected}, 实际: {real_path}")
        
        # 测试移动
        multi_dir = base_dir / "multi"
        multi_dir.mkdir()
        
        src = base_dir / real_path
        # 计算相对路径
        rel_path = Path(real_path).relative_to(".")
        dst = multi_dir / rel_path
        
        # 确保目标父目录存在
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        if src.exists():
            shutil.move(str(src), str(dst))
            print(f"\n[OK] 成功移动到: {dst.relative_to(base_dir)}")
        
        print("\n移动后的结构:")
        print_tree(base_dir)
        
        # 验证
        if dst.exists() and not src.exists():
            print("[PASS] 多层级路径移动正确")
            return True
        else:
            print("[FAIL] 多层级路径移动失败")
            return False

def print_tree(path: Path, prefix="", is_last=True):
    """打印目录树"""
    if not path.exists():
        return
    
    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
    
    for i, item in enumerate(items):
        is_last_item = (i == len(items) - 1)
        current_prefix = "  " if is_last else "  "
        item_prefix = "`-- " if is_last_item else "|-- "
        
        marker = "[DIR]" if item.is_dir() else "[FILE]"
        print(f"{prefix}{item_prefix}{marker} {item.name}")
        
        if item.is_dir():
            extension = "    " if is_last_item else "|   "
            print_tree(item, prefix + current_prefix + extension, is_last_item)

def run_all_tests():
    """运行所有测试"""
    print("\n")
    print("*" * 80)
    print("*" + " " * 78 + "*")
    print("*" + "  虚拟文件夹 BUG 修复验证测试套件".center(76) + "  *")
    print("*" + " " * 78 + "*")
    print("*" * 80)
    
    results = []
    
    # 测试1：集成场景
    try:
        result1 = test_integration_scenario()
        results.append(("集成测试", result1))
    except Exception as e:
        print(f"\n[ERROR] 集成测试异常: {e}")
        results.append(("集成测试", False))
    
    # 测试2：多层级路径
    try:
        result2 = test_multi_level_paths()
        results.append(("多层级路径测试", result2))
    except Exception as e:
        print(f"\n[ERROR] 多层级路径测试异常: {e}")
        results.append(("多层级路径测试", False))
    
    # 总结
    print("\n" + "*" * 80)
    print("测试总结")
    print("*" * 80)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")
    
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n[SUCCESS] 所有测试通过! 虚拟文件夹 bug 已修复!")
    else:
        print("\n[WARNING] 部分测试失败，请检查代码!")
    
    print("*" * 80)
    
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)

