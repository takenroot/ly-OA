@echo off
chcp 65001 >nul
REM 在 Windows 侧打包 exe(需要已装 uv;在仓库根目录执行)
REM --collect-all rapidocr_onnxruntime: 把 ONNX 模型文件打进 exe,缺了跑不起来
REM --collect-all winotify: 把通知库打进 exe
REM --add-data: 把 config.ini / template.json / 参考 xlsx / workshops 打进 exe,首次运行自动释放
uv add --dev pyinstaller
uv run pyinstaller --onefile --name ly-oa --windowed ^
    --collect-all rapidocr_onnxruntime ^
    --collect-all winotify ^
    --add-data "config.ini;." ^
    --add-data "template.json;." ^
    --add-data "使用说明.txt;." ^
    --add-data "参考模板\固废填埋日统计表0809.xlsx;参考模板" ^
    --add-data "workshops;workshops" ^
    run.py
echo.
echo 产出: dist\ly-oa.exe
echo 部署: 只需要复制 dist\ly-oa.exe 到目标目录,双击即可自动生成配置与模板文件
pause
