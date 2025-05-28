"""
测试哈希导出模块功能
"""
import os
import sys
import json
import shutil
from pathlib import Path
import unittest
import tempfile
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from hashu import calculate_hash_for_artist_folder, get_hash_file_path
from hashu.core.calculate_hash_custom import ImgUtils

class TestHashExport(unittest.TestCase):
    """测试哈希导出模块的功能"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建临时目录作为测试文件夹
        self.temp_dir = tempfile.mkdtemp(prefix="hashu_test_")
        self.artist_folder = Path(self.temp_dir) / "[测试画师] 测试作品集"
        self.artist_folder.mkdir(exist_ok=True)
        
        # 创建一些测试图片
        self.test_images = []
        self.create_test_images()
        
    def tearDown(self):
        """测试后的清理工作"""
        # 删除临时目录
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_images(self):
        """创建测试用的图片文件"""
        try:
            # 使用PIL创建一些测试图片
            from PIL import Image
            
            # 创建不同大小的测试图片
            sizes = [(100, 100), (200, 150), (300, 200)]
            colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
            
            for i, (size, color) in enumerate(zip(sizes, colors)):
                img_path = self.artist_folder / f"test_image_{i+1}.png"
                img = Image.new('RGB', size, color=color)
                img.save(img_path)
                self.test_images.append(img_path)
                
            print(f"已创建 {len(self.test_images)} 个测试图片")
            
        except ImportError:
            # 如果没有PIL，创建空文件作为替代
            for i in range(3):
                img_path = self.artist_folder / f"test_image_{i+1}.png"
                img_path.touch()
                self.test_images.append(img_path)
            
            print("警告: 未安装PIL，使用空文件代替测试图片")
    
    def test_calculate_hash_for_artist_folder(self):
        """测试画师文件夹哈希计算功能"""
        print(f"\n开始测试画师文件夹哈希计算，文件夹: {self.artist_folder}")
        
        # 调用函数计算哈希
        hash_file_path = calculate_hash_for_artist_folder(
            self.artist_folder, 
            workers=2, 
            force_update=True
        )
        
        # 验证返回的哈希文件路径
        self.assertIsNotNone(hash_file_path, "哈希计算应该返回有效的文件路径")
        self.assertTrue(os.path.exists(hash_file_path), f"哈希文件应该存在: {hash_file_path}")
        
        # 验证哈希文件路径是否正确
        expected_path = str(self.artist_folder / "image_hashes.json")
        self.assertEqual(hash_file_path, expected_path, "哈希文件应该保存在画师目录下，命名为image_hashes.json")
        
        # 验证哈希文件内容
        with open(hash_file_path, 'r', encoding='utf-8') as f:
            hash_data = json.load(f)
        
        # 检查哈希文件格式是否正确
        self.assertIn("artist_folder", hash_data, "哈希文件应包含artist_folder字段")
        self.assertIn("hashes", hash_data, "哈希文件应包含hashes字段")
        self.assertIn("total_files", hash_data, "哈希文件应包含total_files字段")
        
        # 检查是否所有测试图片都已计算哈希
        expected_count = len(self.test_images)
        actual_count = hash_data.get("success_count", 0)
        
        self.assertEqual(expected_count, actual_count, 
                         f"应成功处理 {expected_count} 个图片，但实际处理了 {actual_count} 个")
        
        # 打印哈希结果摘要
        print(f"哈希文件已生成: {hash_file_path}")
        print(f"总文件数: {hash_data.get('total_files')}")
        print(f"成功处理: {hash_data.get('success_count')}")
        print(f"失败处理: {hash_data.get('error_count')}")
        
        # 检查哈希列表文件是否已更新
        hash_files_list_path = r"E:\999EHV\hash_files_list.txt"
        if os.path.exists(hash_files_list_path):
            with open(hash_files_list_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            self.assertIn(hash_file_path + '\n', lines, "哈希文件路径应该已添加到列表文件中")
    
    def test_force_update(self):
        """测试强制更新功能"""
        # 首先生成一个哈希文件
        hash_file_path = calculate_hash_for_artist_folder(self.artist_folder, workers=2)
        
        # 记录文件的修改时间
        first_mtime = os.path.getmtime(hash_file_path)
        
        # 等待一秒，确保时间戳会有差异
        import time
        time.sleep(1)
        
        # 不强制更新，应该返回相同的文件路径，但不会重新生成
        hash_file_path2 = calculate_hash_for_artist_folder(self.artist_folder, workers=2, force_update=False)
        self.assertEqual(hash_file_path, hash_file_path2, "不强制更新时应返回相同的哈希文件路径")
        
        # 检查文件修改时间是否未变
        second_mtime = os.path.getmtime(hash_file_path)
        self.assertEqual(first_mtime, second_mtime, "不强制更新时文件不应被修改")
        
        # 强制更新，应该重新生成文件
        hash_file_path3 = calculate_hash_for_artist_folder(self.artist_folder, workers=2, force_update=True)
        self.assertEqual(hash_file_path, hash_file_path3, "强制更新时应返回相同的哈希文件路径")
        
        # 检查文件修改时间是否已变
        third_mtime = os.path.getmtime(hash_file_path)
        self.assertNotEqual(second_mtime, third_mtime, "强制更新时文件应被重新生成")
    
    def test_get_hash_file_path(self):
        """测试获取哈希文件路径功能"""
        # 先运行一次哈希计算确保有哈希文件
        hash_file_path = calculate_hash_for_artist_folder(self.artist_folder, workers=2)
        
        # 然后测试获取最新哈希文件路径
        latest_hash_file = get_hash_file_path()
        
        # 验证获取的哈希文件路径
        self.assertIsNotNone(latest_hash_file, "应能获取到最新的哈希文件路径")
        self.assertTrue(os.path.exists(latest_hash_file), "获取的哈希文件应该存在")
    
    def test_empty_folder(self):
        """测试空文件夹的处理"""
        # 创建一个空的画师文件夹
        empty_folder = Path(self.temp_dir) / "[空画师] 无作品"
        empty_folder.mkdir(exist_ok=True)
        
        # 调用函数计算哈希
        hash_file_path = calculate_hash_for_artist_folder(empty_folder, workers=2)
        
        # 验证空文件夹的处理
        self.assertIsNone(hash_file_path, "空文件夹应返回None")
    
    def test_nonexistent_folder(self):
        """测试不存在文件夹的处理"""
        # 构造一个不存在的文件夹路径
        nonexistent_folder = Path(self.temp_dir) / "不存在的文件夹"
        
        # 调用函数计算哈希
        hash_file_path = calculate_hash_for_artist_folder(nonexistent_folder, workers=2)
        
        # 验证不存在文件夹的处理
        self.assertIsNone(hash_file_path, "不存在的文件夹应返回None")

if __name__ == "__main__":
    unittest.main() 