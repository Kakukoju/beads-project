@echo off
REM ============================================
REM 本機 → EC2 反向 SSH 隧道 (Windows)
REM 
REM 功能：將本機 Flask:5100 映射到 EC2 的 127.0.0.1:5100
REM       EC2 nginx 再反向代理給外部存取
REM
REM 前置需求：
REM   1. 安裝 OpenSSH (Windows 10+ 內建)
REM   2. 將 EC2 的 .pem 金鑰放到指定路徑
REM   3. 先手動 SSH 一次確認 host key
REM ============================================

REM ★★★ 修改以下設定 ★★★
SET EC2_IP=52.192.138.213
SET EC2_USER=ec2-user
SET EC2_KEY=C:\Users\harryhrguo\.ssh\beadsmobile.pem
SET LOCAL_PORT=5100
SET REMOTE_PORT=5100

echo ============================================
echo  Beads API 反向隧道
echo  本機 :%LOCAL_PORT% → EC2 %EC2_IP%:%REMOTE_PORT%
echo ============================================
echo.

REM 檢查金鑰檔案
if not exist "%EC2_KEY%" (
    echo ❌ 找不到 EC2 金鑰: %EC2_KEY%
    echo    請將 .pem 檔案放到該路徑
    pause
    exit /b 1
)

REM 先測試 Flask 是否在跑
curl -s http://localhost:%LOCAL_PORT%/ping >nul 2>&1
if errorlevel 1 (
    echo ⚠️  警告: 本機 Flask :%LOCAL_PORT% 似乎沒有啟動
    echo    請先啟動 Flask，否則隧道連上也無法使用
    echo.
)

echo 🔗 正在建立反向隧道...
echo    按 Ctrl+C 中斷
echo.

:LOOP
ssh -N -R 127.0.0.1:%REMOTE_PORT%:127.0.0.1:%LOCAL_PORT% ^
    -i "%EC2_KEY%" ^
    -o ServerAliveInterval=30 ^
    -o ServerAliveCountMax=3 ^
    -o ExitOnForwardFailure=yes ^
    -o StrictHostKeyChecking=no ^
    %EC2_USER%@%EC2_IP%

echo.
echo ⚠️  隧道斷線，5秒後重連...
timeout /t 5 /nobreak >nul
goto LOOP
