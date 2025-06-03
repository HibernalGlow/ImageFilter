"""
编码处理工具模块 - 统一处理7z和压缩包文件名编码问题
"""
import subprocess
import os
from typing import List, Tuple, Optional
from loguru import logger


class EncodingHandler:
    """编码处理工具类"""
    
    @staticmethod
    def detect_system_encoding() -> str:
        """检测系统默认编码"""
        import locale
        try:
            # 获取系统默认编码
            encoding = locale.getpreferredencoding()
            logger.debug(f"检测到系统编码: {encoding}")
            return encoding
        except Exception:
            return 'utf-8'
    
    @staticmethod
    def get_encoding_candidates() -> List[str]:
        """获取编码候选列表，按优先级排序"""
        system_encoding = EncodingHandler.detect_system_encoding()
        
        # Windows常用编码
        windows_encodings = ['cp936', 'gbk', 'cp932', 'shift-jis', 'cp437']
        
        # 构建优先级列表
        candidates = ['utf-8']
        
        # 添加系统编码
        if system_encoding not in candidates:
            candidates.append(system_encoding)
            
        # 添加Windows常用编码
        for enc in windows_encodings:
            if enc not in candidates:
                candidates.append(enc)
                
        # 添加其他编码
        other_encodings = ['gb18030', 'big5', 'euc-jp', 'latin1']
        for enc in other_encodings:
            if enc not in candidates:
                candidates.append(enc)
                
        return candidates
    
    @staticmethod
    def decode_bytes_smart(data: bytes) -> str:
        """智能解码bytes数据"""
        if isinstance(data, str):
            return data
            
        # 尝试不同编码
        encodings = EncodingHandler.get_encoding_candidates()
        
        for encoding in encodings:
            try:
                result = data.decode(encoding)
                # 验证解码结果是否包含明显的乱码标志
                if '�' not in result or encoding == encodings[-1]:
                    logger.debug(f"成功使用编码 {encoding} 解码")
                    return result
            except (UnicodeDecodeError, LookupError):
                continue
                
        # 最后的回退方案
        logger.warning("所有编码尝试失败，使用UTF-8 errors='replace'")
        return data.decode('utf-8', errors='replace')
    
    @staticmethod
    def run_7z_command_safe(cmd: List[str]) -> Tuple[bool, str, str]:
        """
        安全地运行7z命令，正确处理编码
        
        Args:
            cmd: 7z命令列表
            
        Returns:
            (success, stdout, stderr)
        """
        try:
            # 在Windows上设置启动信息以隐藏窗口
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            
            # 使用bytes模式运行，避免编码问题
            result = subprocess.run(
                cmd,
                capture_output=True,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            
            # 智能解码输出
            stdout = EncodingHandler.decode_bytes_smart(result.stdout) if result.stdout else ""
            stderr = EncodingHandler.decode_bytes_smart(result.stderr) if result.stderr else ""
            
            success = result.returncode == 0
            
            if not success:
                logger.debug(f"7z命令失败: {' '.join(cmd)}")
                logger.debug(f"错误输出: {stderr}")
            
            return success, stdout, stderr
            
        except Exception as e:
            logger.error(f"执行7z命令失败: {e}")
            return False, "", str(e)
    
    @staticmethod
    def normalize_filename(filename: str) -> str:
        """标准化文件名，移除可能的乱码字符"""
        if not filename:
            return filename
            
        # 移除常见的乱码字符
        normalized = filename.replace('�', '')
        
        # 如果文件名变成空的，使用原始文件名
        if not normalized.strip():
            return filename
            
        return normalized
    
    @staticmethod
    def validate_encoding_result(text: str) -> bool:
        """验证编码结果是否正确"""
        if not text:
            return True
            
        # 检查是否包含大量乱码字符
        replacement_char_count = text.count('�')
        total_chars = len(text)
        
        if total_chars == 0:
            return True
            
        # 如果乱码字符超过20%，认为编码可能有问题
        replacement_ratio = replacement_char_count / total_chars
        return replacement_ratio < 0.2


class ZipFilenameDecoder:
    """ZIP文件名解码器，增强版本"""
    
    @staticmethod
    def decode_zip_filename(name_bytes: bytes, zip_flags: int = 0) -> str:
        """
        解码ZIP文件名，支持多种编码
        
        Args:
            name_bytes: 文件名的bytes数据
            zip_flags: ZIP标志位
            
        Returns:
            解码后的文件名
        """
        if isinstance(name_bytes, str):
            return name_bytes
            
        # 检查UTF-8标志位
        if (zip_flags & 0x800) != 0:
            try:
                result = name_bytes.decode('utf-8')
                if EncodingHandler.validate_encoding_result(result):
                    return result
            except UnicodeDecodeError:
                pass
        
        # 尝试字符检测
        try:
            import chardet
            detected = chardet.detect(name_bytes)
            if detected and detected['confidence'] > 0.7:
                try:
                    result = name_bytes.decode(detected['encoding'])
                    if EncodingHandler.validate_encoding_result(result):
                        return result
                except (UnicodeDecodeError, LookupError):
                    pass
        except ImportError:
            pass
        
        # 使用智能解码
        return EncodingHandler.decode_bytes_smart(name_bytes)
