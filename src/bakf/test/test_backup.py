import os
import shutil
import zipfile
import tempfile
import pytest
from bakf.core.backup import BackupHandler

def create_test_zip(zip_path, files):
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for arcname, content in files.items():
            zf.writestr(arcname, content)

def read_zip_files(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        return set(zf.namelist())

def test_backup_from_archive(tmp_path):
    # 创建测试zip
    zip_path = tmp_path / 'test.zip'
    files = {
        'a.txt': b'hello',
        'b/b.txt': b'world',
        'c/c.txt': b'python'
    }
    create_test_zip(zip_path, files)
    # 备份a.txt和b/b.txt
    to_backup = {'a.txt', 'b/b.txt'}
    reasons = {'a.txt': {'reason': 'ad'}, 'b/b.txt': {'reason': 'hash'}}
    result = BackupHandler.backup_from_archive(str(zip_path), to_backup, reasons)
    trash_dir = tmp_path / 'test.trash'
    assert (trash_dir / 'ad' / 'a.txt').exists()
    assert (trash_dir / 'hash' / 'b' / 'b.txt').exists()
    assert result['a.txt'] is True
    assert result['b/b.txt'] is True

def test_backup_source_file(tmp_path):
    file_path = tmp_path / 'origin.zip'
    file_path.write_bytes(b'123456')
    ok, bak_path = BackupHandler.backup_source_file(str(file_path))
    assert ok
    assert os.path.exists(bak_path)
    # 再次备份，生成.bak1
    ok2, bak_path2 = BackupHandler.backup_source_file(str(file_path))
    assert ok2
    assert bak_path2.endswith('.bak1')

def test_process_archive_delete(tmp_path):
    # 创建测试zip
    zip_path = tmp_path / 'del.zip'
    files = {
        'x.txt': b'xx',
        'y/y.txt': b'yy',
        'z/z.txt': b'zz'
    }
    create_test_zip(zip_path, files)
    # 删除x.txt和z/z.txt
    to_delete = {'x.txt', 'z/z.txt'}
    reasons = {'x.txt': {'reason': 'ad'}, 'z/z.txt': {'reason': 'hash'}}
    ok, msg = BackupHandler.process_archive_delete(str(zip_path), to_delete, reasons)
    assert ok, msg
    # 检查zip内容
    remain = read_zip_files(zip_path)
    assert 'x.txt' not in remain
    assert 'z/z.txt' not in remain
    assert 'y/y.txt' in remain
    # 检查.trash备份
    trash_dir = tmp_path / 'del.trash'
    assert (trash_dir / 'ad' / 'x.txt').exists()
    assert (trash_dir / 'hash' / 'z' / 'z.txt').exists() 