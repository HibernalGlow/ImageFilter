from huggingface_hub import hf_hub_download  
  
# 单色图片检测模型  
hf_hub_download(  
    repo_id='deepghs/monochrome_detect',  
    filename='mobilenetv3_large_100_dist_safe2/model.onnx'  
)  
  
# 线稿检测模型  
hf_hub_download(  
    repo_id='deepghs/imgutils-models',  
    filename='lineart/lineart.onnx'  
)  
  
# OCR模型  
hf_hub_download(  
    repo_id='deepghs/paddleocr',  
    filename='det/ch_PP-OCRv4_det/model.onnx'  
)  
hf_hub_download(  
    repo_id='deepghs/paddleocr',  
    filename='rec/ch_PP-OCRv4_rec/model.onnx'  
)  
  
print("所有模型已成功下载到本地缓存")