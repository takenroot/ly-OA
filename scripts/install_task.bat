@echo off
chcp 65001 >nul
REM 注册每天 08:30 自动跑前一天的日报(放在 ly-oa.exe 同目录,双击一次即可)
REM 注意: 若定时时电脑关机,当天不会补跑,用 补跑.bat 手动补
schtasks /create /tn "收料单日报" /tr "\"%~dp0ly-oa.exe\" --auto" /sc daily /st 08:30 /f
echo.
echo 已注册。手动验证: schtasks /run /tn "收料单日报"
pause
