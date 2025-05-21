"""
数字缩写转换模块
提供数字转中文习惯缩写格式的功能（支持万/亿单位）
"""

def shorten_number_cn(
    number: int, 
    precision: int = 1,
    use_w: bool = True
) -> str:
    """
    将大数字转换为中文习惯的缩写格式
    
    Args:
        number: 要转换的数字
        precision: 小数位精度（默认1位）
        use_w: 是否使用"万"为单位（True时万进制，False时千进制）
    
    Returns:
        str: 格式化后的字符串
        
    Examples:
        >>> shorten_number_cn(18500)
        '1.8w'
        >>> shorten_number_cn(215_0000)
        '215w'
        >>> shorten_number_cn(3_5000_0000)
        '3.5亿'
    """
    number=round(number)
    if number < 1000:
        return str(number)
        
    if use_w:
        # 万进制处理
        if number >= 1_0000_0000:
            # 亿单位处理
            value = number / 1_0000_0000
            unit = '亿'
        elif number >= 1_0000:
            # 万单位处理
            value = number / 1_0000
            unit = 'w'
        else:
            # 千单位处理（当小于1万时）
            value = number / 1000
            unit = 'k'
    else:
        # 千进制处理
        if number >= 1_000_000_000:
            value = number / 1_000_000_000
            unit = 'B'
        elif number >= 1_000_000:
            value = number / 1_000_000
            unit = 'M'
        else:
            value = number / 1000
            unit = 'k'

    # 处理精度
    if value == int(value):
        # 整数情况省略小数部分
        return f"{int(value)}{unit}"
    else:
        # 保留指定位数小数
        return f"{value:.{precision}f}{unit}".rstrip('0').rstrip('.') 

def demo():
    """演示数字缩写功能"""
    test_cases = [
        (999.99, "999"),
        (1850, "1.8k"),
        (21500.24566, "2.1w"),
        (3_5000_0000, "3.5亿"),
        (123_4567, "123.5w"),
        (9999, "9999"),
        (10000, "1w"),
        (1_0500, "1.1w"),
        (12_3456_7890, "12.3亿"),
        (1500, "1.5k"),
    ]
    
    print("┌───────────────────────┬──────────────┐")
    print("│ 原始数字              │ 转换结果     │")
    print("├───────────────────────┼──────────────┤")
    for num, expected in test_cases:
        result = shorten_number_cn(num)
        print(f"│ {str(num).ljust(21)} │ {result.ljust(12)} │")
    print("└───────────────────────┴──────────────┘")

if __name__ == "__main__":
    demo() 