import numpy as np
from typing import List, Tuple, Dict, Optional
from loguru import logger
class HashAccelerator:
    """使用NumPy加速哈希计算和比较的类"""
    
    @staticmethod
    def hex_to_binary_array(hex_str: str) -> np.ndarray:
        """将16进制哈希字符串转换为二进制NumPy数组
        
        Args:
            hex_str: 16进制哈希字符串
            
        Returns:
            np.ndarray: 二进制数组
        """
        try:
            # 统一转换为小写
            hex_str = hex_str.lower()
            # 将16进制字符串转换为整数
            num = int(hex_str, 16)
            # 获取二进制字符串
            bin_str = format(num, f'0{len(hex_str)*4}b')
            # 转换为NumPy数组
            return np.array([int(b) for b in bin_str], dtype=np.uint8)
        except Exception as e:
            logger.error(f"转换哈希值失败: {e}")
            return None

    @staticmethod
    def preprocess_hash_list(hash_list: List[str]) -> np.ndarray:
        """预处理哈希值列表为二进制矩阵
        
        Args:
            hash_list: 哈希值字符串列表
            
        Returns:
            np.ndarray: 二进制矩阵，每行代表一个哈希值
        """
        try:
            if not hash_list:
                return np.array([])
                
            # 获取第一个有效哈希的长度
            first_hash = next((h for h in hash_list if h), None)
            if not first_hash:
                return np.array([])
                
            bit_length = len(first_hash) * 4  # 每个16进制字符代表4位
            hash_matrix = np.zeros((len(hash_list), bit_length), dtype=np.uint8)
            
            for i, hash_str in enumerate(hash_list):
                if not hash_str:
                    continue
                binary = HashAccelerator.hex_to_binary_array(hash_str)
                if binary is not None:
                    hash_matrix[i] = binary
                    
            return hash_matrix
        except Exception as e:
            logger.error(f"预处理哈希列表失败: {e}")
            return np.array([])

    @staticmethod
    def calculate_hamming_distances(target_hash: str, ref_hashes: List[str]) -> np.ndarray:
        """计算目标哈希值与参考哈希值列表的汉明距离
        
        Args:
            target_hash: 目标哈希值
            ref_hashes: 参考哈希值列表
            
        Returns:
            np.ndarray: 汉明距离数组
        """        
        try:
            # 转换目标哈希
            target_binary = HashAccelerator.hex_to_binary_array(target_hash)
            if target_binary is None:
                return np.array([])
                
            # 预处理参考哈希列表
            ref_matrix = HashAccelerator.preprocess_hash_list(ref_hashes)
            if ref_matrix.size == 0:
                return np.array([])
                
            # 检查维度是否匹配
            if target_binary.shape[0] != ref_matrix.shape[1]:
                logger.error(f"哈希长度不匹配: target={target_binary.shape[0]}, ref={ref_matrix.shape[1]}")
                return np.array([])
                
            # 使用NumPy的广播机制计算汉明距离
            distances = np.sum(target_binary != ref_matrix, axis=1)
            return distances
            
        except Exception as e:
            logger.error(f"计算汉明距离失败: {e}")
            return np.array([])

    @staticmethod
    def find_similar_hashes(target_hash: str, ref_hashes: List[str], 
                          hash_to_uri: Dict[str, str], threshold: int, 
                          target_uri: Optional[str] = None) -> List[Tuple[str, str, int]]:
        """查找所有相似的哈希值
        
        Args:
            target_hash: 目标哈希值
            ref_hashes: 参考哈希值列表
            hash_to_uri: 哈希值到URI的映射
            threshold: 汉明距离阈值
            target_uri: 目标文件的URI，用于排除自身
            
        Returns:
            List[Tuple[str, str, int]]: 相似哈希列表，每个元素为(哈希值, URI, 汉明距离)
        """
        try:
            # 计算所有汉明距离
            distances = HashAccelerator.calculate_hamming_distances(target_hash, ref_hashes)
            if distances.size == 0:
                return []
                
            # 找出所有小于等于阈值的索引
            similar_indices = np.where(distances <= threshold)[0]
            
            # 收集结果
            results = []
            for idx in similar_indices:
                ref_hash = ref_hashes[idx]
                uri = hash_to_uri.get(ref_hash)
                distance = int(distances[idx])
                
                if uri:
                    # 如果汉明距离为0且是同一个文件，则排除
                    if distance == 0 and target_uri and uri == target_uri:
                        continue
                    results.append((ref_hash, uri, distance))
                    
            return results
            
        except Exception as e:
            logger.error(f"查找相似哈希失败: {e}")
            return []    @staticmethod
    def batch_find_similar_hashes(target_hashes: List[str], ref_hashes: List[str],
                                hash_to_uri: Dict[str, str], threshold: int,
                                target_hash_to_uri: Optional[Dict[str, str]] = None) -> Dict[str, List[Tuple[str, str, int]]]:
        """批量查找相似哈希值
        
        Args:
            target_hashes: 目标哈希值列表
            ref_hashes: 参考哈希值列表
            hash_to_uri: 哈希值到URI的映射
            threshold: 汉明距离阈值
            target_hash_to_uri: 目标哈希值到URI的映射，用于排除自身
            
        Returns:
            Dict[str, List[Tuple[str, str, int]]]: 每个目标哈希对应的相似哈希列表
        """
        try:
            # 预处理参考哈希矩阵
            ref_matrix = HashAccelerator.preprocess_hash_list(ref_hashes)
            if ref_matrix.size == 0:
                return {}
                
            results = {}
            for target_hash in target_hashes:
                if not target_hash:
                    continue
                    
                # 转换目标哈希
                target_binary = HashAccelerator.hex_to_binary_array(target_hash)
                if target_binary is None:
                    continue
                    
                # 计算与所有参考哈希的距离
                distances = np.sum(target_binary != ref_matrix, axis=1)
                
                # 找出相似的哈希
                similar_indices = np.where(distances <= threshold)[0]
                similar_hashes = []
                
                # 获取目标文件的URI
                target_uri = target_hash_to_uri.get(target_hash) if target_hash_to_uri else None
                
                for idx in similar_indices:
                    ref_hash = ref_hashes[idx]
                    uri = hash_to_uri.get(ref_hash)
                    distance = int(distances[idx])
                    
                    if uri:
                        # 如果汉明距离为0且是同一个文件，则排除
                        if distance == 0 and target_uri and uri == target_uri:
                            continue
                        similar_hashes.append((ref_hash, uri, distance))
                        
                if similar_hashes:
                    results[target_hash] = similar_hashes
                    
            return results
            
        except Exception as e:
            logger.error(f"批量查找相似哈希失败: {e}")
            return {}