@echo off
echo ===========================================
echo    pHash 图片相似度分析工具
echo ===========================================
echo.
echo 正在启动 Streamlit 应用...
echo 浏览器将自动打开，如果没有请手动访问显示的URL
echo 按 Ctrl+C 停止应用
echo.

cd /d "%~dp0"
python run_streamlit.py

pause
