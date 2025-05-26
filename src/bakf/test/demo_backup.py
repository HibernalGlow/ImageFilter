import os
import zipfile
from bakf.core.backup import BackupHandler

def create_test_zip(zip_path, files):
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for arcname, content in files.items():
            zf.writestr(arcname, content)

def print_dir_tree(root):
    for dirpath, dirnames, filenames in os.walk(root):
        level = dirpath.replace(str(root), '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(dirpath)}/")
        for f in filenames:
            print(f"{indent}  {f}")

def print_zip_content(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        print("Zip内容：", zf.namelist())

if __name__ == "__main__":
    # 1. 创建测试zip
    work_dir = os.path.abspath('./demo_tmp')
    os.makedirs(work_dir, exist_ok=True)
    zip_path = os.path.join(work_dir, 'demo.zip')
    files = {
        'a.txt': b'hello',
        'b/b.txt': b'world',
        'c/c.txt': b'python'
    }
    create_test_zip(zip_path, files)
    print("初始zip内容：")
    print_zip_content(zip_path)

    # 2. 备份a.txt和b/b.txt到.trash
    to_backup = {'a.txt', 'b/b.txt'}
    reasons = {'a.txt': {'reason': 'ad'}, 'b/b.txt': {'reason': 'hash'}}
    BackupHandler.backup_from_archive(zip_path, to_backup, reasons)
    print("\n.trash 目录结构：")
    trash_dir = os.path.join(work_dir, 'demo.trash')
    print_dir_tree(trash_dir)

    # 3. 备份并删除a.txt和c/c.txt
    to_delete = {'a.txt', 'c/c.txt'}
    reasons2 = {'a.txt': {'reason': 'ad'}, 'c/c.txt': {'reason': 'hash'}}
    BackupHandler.process_archive_delete(zip_path, to_delete, reasons2)
    print("\n删除后zip内容：")
    print_zip_content(zip_path)
    print("\n.trash 目录结构（含新备份）：")
    print_dir_tree(trash_dir)