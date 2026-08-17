@echo off
chcp 65001 >nul
REM 手动补跑/复现某一天: 扫描 config.ini 里所有数据源,合并生成该日日报
set /p d=输入要补跑的日期(格式 2026-8-11):
"%~dp0ly-oa.exe" --day %d%
echo.
echo 结果见 logs/ 和 各数据源目录下
pause
