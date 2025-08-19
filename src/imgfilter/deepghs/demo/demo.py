from PIL import Image, ImageDraw  
import pillow_avif
import pillow_jxl
import numpy as np  
import os  
import sys

# 设置环境变量以禁用SSL验证，解决证书问题
os.environ['HF_HUB_DISABLE_SSL_VERIFICATION'] = '1'
os.environ['CURL_CA_BUNDLE'] = ''

  
# 导入单色图片检测功能  
from imgutils.validate import get_monochrome_score, is_monochrome  
# 导入图片差分检测功能  
from imgutils.metrics import lpips_difference, lpips_clustering  
# 导入线稿检测功能  
from imgutils.edge import get_edge_by_lineart, edge_image_with_lineart  
from imgutils.edge import get_edge_by_lineart_anime, edge_image_with_lineart_anime  
from imgutils.edge import get_edge_by_canny, edge_image_with_canny  
from imgutils.ocr import detect_text_with_ocr, ocr, list_det_models, list_rec_models  

def demo_ocr_detection(image_path):  
    """演示OCR文本检测功能"""  
    print("\n=== OCR文本检测演示 ===")  
      
    # 加载原始图像  
    original_image = Image.open(image_path)  
      
    # 1. 仅检测文本区域  
    text_regions = detect_text_with_ocr(image_path)  
      
    # 2. 完整OCR（检测+识别）  
    ocr_results = ocr(image_path)  
      
    # 保存文本区域检测结果图像
    img_with_regions = original_image.copy()  
    draw = ImageDraw.Draw(img_with_regions)  
    for (x0, y0, x1, y1), _, score in text_regions:  
        draw.rectangle([(x0, y0), (x1, y1)], outline="red", width=2)  
    img_with_regions.save("ocr_text_regions.png")
    print(f"文本区域检测图像已保存为 ocr_text_regions.png (检测到{len(text_regions)}个区域)")
      
    # 保存OCR识别结果图像
    img_with_ocr = original_image.copy()  
    draw = ImageDraw.Draw(img_with_ocr)  
    for (x0, y0, x1, y1), text, score in ocr_results:  
        draw.rectangle([(x0, y0), (x1, y1)], outline="blue", width=2)  
        draw.text((x0, y0-15), text, fill="blue")  
    img_with_ocr.save("ocr_text_recognition.png")
    print(f"OCR文本识别图像已保存为 ocr_text_recognition.png (识别到{len(ocr_results)}个文本)")
      
    # 打印模型信息
    det_models = list_det_models()  
    rec_models = list_rec_models()  
    print(f"\n可用检测模型: {len(det_models)}个")  
    print(f"示例: {', '.join(det_models[:3])}...")  
    print(f"\n可用识别模型: {len(rec_models)}个")  
    print(f"示例: {', '.join(rec_models[:3])}...")  
      
    # 打印详细OCR结果  
    print("\nOCR识别结果:")  
    for i, (bbox, text, score) in enumerate(ocr_results):  
        print(f"{i+1}. 文本: '{text}', 置信度: {score:.4f}, 位置: {bbox}")
    print("OCR文本检测完成")
def demo_monochrome_detection(image_paths):  
    """演示单色图片检测功能"""  
    print("=== 单色图片检测演示 ===")  
      
    for i, img_path in enumerate(image_paths):  
        # 加载图像  
        image = Image.open(img_path)  
          
        # 获取单色分数和判断结果  
        mono_score = get_monochrome_score(img_path)  
        is_mono = is_monochrome(img_path)  
          
        # 显示结果  
        result = "单色" if is_mono else "彩色"  
        print(f"{i+1}. {os.path.basename(img_path)}: {result} (分数: {mono_score:.4f})")
        
        # 保存带标注的图片
        img_copy = image.copy()
        draw = ImageDraw.Draw(img_copy)
        # 在图片上添加文本标注
        draw.text((10, 10), f"{result} (分数: {mono_score:.4f})", fill="red")
        output_path = f"monochrome_{i+1}_{os.path.basename(img_path)}"
        img_copy.save(output_path)
        print(f"   标注图片已保存为: {output_path}")
      
    print("单色图片检测完成")
  
def demo_image_difference(image_paths):  
    """演示图片差分检测功能"""  
    print("\n=== 图片差分检测演示 ===")  
      
    # 计算图片间的差异矩阵  
    n = len(image_paths)  
    diff_matrix = np.zeros((n, n))  
    print("正在计算图片差异矩阵...")
    for i in range(n):  
        for j in range(i+1, n):  
            print(f"计算 {os.path.basename(image_paths[i])} 与 {os.path.basename(image_paths[j])} 的差异...")
            diff = lpips_difference(image_paths[i], image_paths[j])  
            diff_matrix[i, j] = diff  
            diff_matrix[j, i] = diff  
            print(f"差异值: {diff:.4f}")
      
    # 进行聚类  
    print("正在进行图片聚类...")
    clusters = lpips_clustering(image_paths)  
      
    # 显示结果  
    print("\n=== 差异矩阵结果 ===")
    print("图片文件名:")
    for i, img_path in enumerate(image_paths):
        print(f"{i}: {os.path.basename(img_path)}")
    
    print("\n差异矩阵:")
    print(f"{'':>15}", end="")
    for i in range(n):
        print(f"{i:>8}", end="")
    print()
    
    for i in range(n):
        print(f"{i:>2} {os.path.basename(image_paths[i])[:12]:>12}", end="")
        for j in range(n):
            print(f"{diff_matrix[i,j]:>8.4f}", end="")
        print()
      
    # 显示聚类结果
    print(f"\n=== 聚类结果 ===")
    for i, (img_path, cluster) in enumerate(zip(image_paths, clusters)):  
        cluster_label = "噪声" if cluster == -1 else f"聚类 {cluster}"  
        print(f"{i+1}. {os.path.basename(img_path)}: {cluster_label}")
        
        # 保存聚类标注的图片
        img = Image.open(img_path)
        img_copy = img.copy()
        draw = ImageDraw.Draw(img_copy)
        draw.text((10, 10), cluster_label, fill="red")
        output_path = f"cluster_{i+1}_{cluster_label.replace(' ', '_')}_{os.path.basename(img_path)}"
        img_copy.save(output_path)
        print(f"   标注图片已保存为: {output_path}")
      
    print("图片差分检测完成")  
    print(f"聚类结果: {clusters}")
  
def demo_edge_detection(image_path):  
    """演示线稿检测功能"""  
    print("\n=== 线稿检测演示 ===")  
      
    # 加载原始图像  
    original_image = Image.open(image_path)  
      
    # 使用不同方法生成线稿  
    lineart_image = edge_image_with_lineart(image_path)  
    lineart_anime_image = edge_image_with_lineart_anime(image_path)  
    canny_image = edge_image_with_canny(image_path)  
      
    # 保存结果图像
    lineart_image.save("edge_lineart.png")
    print("Lineart 线稿已保存为 edge_lineart.png")
    
    lineart_anime_image.save("edge_lineart_anime.png")
    print("Lineart Anime 线稿已保存为 edge_lineart_anime.png")
    
    canny_image.save("edge_canny.png")
    print("Canny 线稿已保存为 edge_canny.png")
    
    print("线稿检测完成，所有结果图像已保存")

def get_valid_image_path(prompt="请输入图像文件路径: "):
    """获取有效的图像文件路径"""
    while True:
        image_path = input(prompt)
        
        # 验证文件路径是否有效
        if not os.path.exists(image_path):
            print(f"错误: 文件 '{image_path}' 不存在，请重新输入有效的图像路径。")
            continue
            
        # 验证是否为图像文件
        try:
            Image.open(image_path)
            return image_path  # 如果能成功打开图像，返回路径
        except Exception as e:
            print(f"错误: 无法打开图像文件: {e}")
            print("请确保输入的是有效的图像文件路径。")

def get_multiple_image_paths(prompt="请输入图像文件路径（输入'完成'结束）: ", min_count=1):
    """获取多个有效的图像文件路径"""
    image_paths = []
    print(f"{prompt} (至少需要{min_count}个图像，输入'完成'结束)")
    
    while len(image_paths) < min_count or (len(image_paths) >= min_count and input("继续添加图像? (y/n): ").lower() == 'y'):
        if len(image_paths) >= min_count:
            path_input = input(f"请输入第{len(image_paths)+1}个图像路径（或输入'完成'结束）: ")
            if path_input.lower() == '完成':
                break
        else:
            path_input = input(f"请输入第{len(image_paths)+1}个图像路径: ")
        
        # 验证文件路径是否有效
        if not os.path.exists(path_input):
            print(f"错误: 文件 '{path_input}' 不存在，请重新输入。")
            continue
            
        # 验证是否为图像文件
        try:
            Image.open(path_input)
            image_paths.append(path_input)
            print(f"已添加图像: {path_input}")
        except Exception as e:
            print(f"错误: 无法打开图像文件: {e}")
            print("请确保输入的是有效的图像文件路径。")
    
    return image_paths
  
def main():  
    """主函数"""  
    print("imgutils 项目特性演示")  
    print("---------------------")  
      
    # 交互获取图像选择
    while True:
        print("\n请选择要演示的功能:")
        print("1. 单色图片检测演示")
        print("2. 图片差分检测演示")
        print("3. 线稿检测演示")
        print("4. 全部演示")
        print("0. 退出程序")
        
        choice = input("请输入选项 (0-4): ")
        
        if choice == "0":
            print("程序已退出。")
            sys.exit(0)
        elif choice in ["1", "4"]:
            # 单色图片检测示例
            print("\n===== 单色图片检测功能 =====")
            print("为了进行单色图片检测，需要提供多张图像样本(建议同时包含单色和彩色图像)。")
            mono_images = get_multiple_image_paths("请输入图像路径", min_count=2)
            if mono_images:
                demo_monochrome_detection(mono_images)
        
        if choice in ["2", "4"]:
            # 图片差分检测示例
            print("\n===== 图片差分检测功能 =====")
            print("为了进行图片差分检测，需要提供多张图像样本(建议至少3-6张图像，可以有相似的)。")
            diff_images = get_multiple_image_paths("请输入图像路径", min_count=3)
            if diff_images:
                demo_image_difference(diff_images)
        
        if choice in ["3", "4"]:
            # 线稿检测示例
            print("\n===== 线稿检测功能 =====")
            print("为了进行线稿检测，需要提供一张图像(推荐使用动漫或者含有线条的图像)。")
            edge_image = get_valid_image_path("请输入一张图像路径: ")
            if edge_image:
                demo_edge_detection(edge_image)
                
        if choice not in ["0", "1", "2", "3", "4"]:
            print("错误: 无效的选项，请重新输入。")
        
        if choice != "4":  # 如果不是全部演示，询问是否继续
            continue_choice = input("\n是否继续演示其他功能? (y/n): ")
            if continue_choice.lower() != 'y':
                print("程序已退出。")
                break
  
if __name__ == "__main__":  
    main()