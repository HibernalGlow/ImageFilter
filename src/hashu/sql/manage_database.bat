@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: 图片哈希数据库管理脚本
echo ==========================================
echo    图片哈希数据库管理工具
echo ==========================================
echo.

:: 设置默认参数
set "POSTGRES_HOST=localhost"
set "POSTGRES_PORT=5432"
set "POSTGRES_USER=postgres"
set "POSTGRES_DB=image_hashes"

:: 检查是否提供了密码
if "%POSTGRES_PASSWORD%"=="" (
    echo 请设置 POSTGRES_PASSWORD 环境变量或在命令中提供密码
    echo 例如: set POSTGRES_PASSWORD=your_password
    echo.
)

:: 检查Python环境
python -c "import asyncpg" 2>nul
if errorlevel 1 (
    echo ❌ 缺少必要的Python包，请安装：
    echo    pip install asyncpg
    echo.
    pause
    exit /b 1
)

:: 显示菜单
:menu
echo 请选择操作:
echo.
echo 1. 检查数据库状态
echo 2. 初始化数据库 (创建表结构)
echo 3. 创建新数据库并初始化
echo 4. 升级数据库结构
echo 5. 从JSON文件迁移数据
echo 6. 清理重复记录
echo 7. 优化数据库
echo 8. 导出统计信息
echo 9. 显示连接信息
echo 0. 退出
echo.
set /p choice="请输入选择 (0-9): "

if "%choice%"=="1" goto status
if "%choice%"=="2" goto init
if "%choice%"=="3" goto init_with_db
if "%choice%"=="4" goto upgrade
if "%choice%"=="5" goto migrate
if "%choice%"=="6" goto cleanup
if "%choice%"=="7" goto optimize
if "%choice%"=="8" goto export_stats
if "%choice%"=="9" goto show_info
if "%choice%"=="0" goto exit

echo 无效选择，请重试
goto menu

:status
echo.
echo 🔍 检查数据库状态...
python database_manager.py status --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB%
echo.
pause
goto menu

:init
echo.
echo 🚀 初始化数据库结构...
python init_database.py --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB%
echo.
pause
goto menu

:init_with_db
echo.
echo 🚀 创建数据库并初始化结构...
python init_database.py --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB% --create-db
echo.
pause
goto menu

:upgrade
echo.
echo ⬆️ 升级数据库结构...
python database_manager.py upgrade --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB%
echo.
pause
goto menu

:migrate
echo.
echo 📂 从JSON文件迁移数据...
echo.
echo 请提供JSON文件路径 (多个文件用空格分隔):
set /p json_files="JSON文件路径: "
if "%json_files%"=="" (
    echo 未提供文件路径
    goto menu
)
python database_manager.py migrate --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB% %json_files%
echo.
pause
goto menu

:cleanup
echo.
echo 🧹 清理重复记录...
python database_manager.py cleanup --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB%
echo.
pause
goto menu

:optimize
echo.
echo 🔧 优化数据库...
python database_manager.py optimize --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB%
echo.
pause
goto menu

:export_stats
echo.
echo 📊 导出统计信息...
set "output_file=database_stats_%date:~0,4%%date:~5,2%%date:~8,2%.json"
python database_manager.py export-stats --host=%POSTGRES_HOST% --port=%POSTGRES_PORT% --user=%POSTGRES_USER% --database=%POSTGRES_DB% --output="%output_file%"
echo.
pause
goto menu

:show_info
echo.
echo 📋 当前连接信息:
echo    主机: %POSTGRES_HOST%
echo    端口: %POSTGRES_PORT%
echo    用户: %POSTGRES_USER%
echo    数据库: %POSTGRES_DB%
echo    密码: %POSTGRES_PASSWORD%
echo.
echo 💡 修改连接信息请编辑此脚本或设置环境变量
echo.
pause
goto menu

:exit
echo.
echo 👋 再见！
pause
exit /b 0
