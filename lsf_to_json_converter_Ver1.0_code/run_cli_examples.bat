@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 查看版本：
python main.py version

echo.
echo 查看帮助：
python main.py --help

echo.
echo 示例：扫描当前目录下的 LSF 文件：
python main.py scan -i . -r --limit 20
pause
