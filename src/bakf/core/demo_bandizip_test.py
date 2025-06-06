import os
import subprocess
import zipfile
import shutil
from pathlib import Path

def create_test_zip(zip_path, test_files):
    """创建测试用的zip文件，包含指定的文件结构"""
    # 创建测试目录
    temp_dir = Path('temp_for_zip')
    temp_dir.mkdir(exist_ok=True)
    
    try:
        # 创建测试文件
        for file_path, content in test_files.items():
            # 确保父目录存在
            file_path = temp_dir / file_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件内容
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        # 创建zip文件
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for file_path in test_files.keys():
                zf.write(temp_dir / file_path, file_path)
        
        print(f"测试zip文件已创建: {zip_path}")
        return True
    except Exception as e:
        print(f"创建测试zip文件失败: {e}")
        return False
    finally:
        # 清理临时目录
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def extract_partial_bandizip(zip_path, arc_path, dest_dir):
    """使用Bandizip提取zip中的特定文件"""
    os.makedirs(dest_dir, exist_ok=True)
    # 找到bz.exe路径，默认安装位置
    bz_path = r'C:\Program Files\Bandizip\bz.exe'  
    
    # 如果没有找到，尝试另一个常见位置
    if not os.path.exists(bz_path):
        bz_path = r'C:\Program Files (x86)\Bandizip\bz.exe'
    
    # 如果还是没找到，假设bz在PATH中
    if not os.path.exists(bz_path):
        bz_path = 'bz'
    
    cmd = [
        bz_path,
        'x',
        f'-o:{dest_dir}',
        str(zip_path),
        arc_path
    ]
    print(f"\n运行命令：{' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True)
        print(f"返回码：{result.returncode}")
        stdout = result.stdout.decode('utf-8', errors='ignore')
        stderr = result.stderr.decode('utf-8', errors='ignore')
        
        if stdout:
            print(f"标准输出：\n{stdout}")
        if stderr:
            print(f"错误输出：\n{stderr}")
        
        # 检查文件是否成功提取
        expected_file = os.path.join(dest_dir, os.path.basename(arc_path))
        arc_path_parts = arc_path.replace('\\', '/').split('/')
        
        # 检查两种可能的路径
        possible_paths = [
            os.path.join(dest_dir, os.path.basename(arc_path)),  # 直接在目标目录
            os.path.join(dest_dir, *arc_path_parts)  # 保持原始路径结构
        ]
        
        file_found = False
        found_path = None
        
        for path in possible_paths:
            if os.path.exists(path):
                file_found = True
                found_path = path
                break
                
        if result.returncode == 0 and file_found:
            print(f"✅ 提取成功: {found_path}")
            # 显示文件内容
            try:
                with open(found_path, 'r', encoding='utf-8') as f:
                    print(f"文件内容:\n{f.read()}")
            except Exception as e:
                print(f"读取文件内容失败: {e}")
            return True
        else:
            print(f"❌ 提取失败: 文件不存在")
            print(f"检查路径: {possible_paths}")
            return False
    except Exception as e:
        print(f"❌ 提取过程出错: {e}")
        return False

def main():
    """主测试函数"""
    # 测试路径
    test_dir = Path('test_bandizip')
    test_dir.mkdir(exist_ok=True)
    
    zip_path = test_dir / 'test.zip'
    extract_dir = test_dir / 'output'
    
    # 要测试的文件
    test_files = {
        'folder1/test1.txt': '这是测试文件1的内容',
        'folder1/test2.txt': '这是测试文件2的内容',
        'folder2/test3.txt': '这是测试文件3的内容',
        'test_root.txt': '这是根目录的测试文件'
    }
    
    # 创建测试zip
    if create_test_zip(zip_path, test_files):
        print("\n==== 测试Bandizip提取特定文件 ====")
        
        # 测试提取不同的文件
        files_to_extract = [
            'folder1/test1.txt',
            'test_root.txt'
        ]
        
        for file in files_to_extract:
            print(f"\n提取文件: {file}")
            extract_partial_bandizip(zip_path, file, extract_dir)
    
    print("\n测试完成，测试文件位于:", test_dir.absolute())

if __name__ == '__main__':
    main() 