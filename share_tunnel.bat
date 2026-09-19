@echo off
echo ===================================================
echo  CampusPrint - Cloudflare Public Tunnel for Review
echo ===================================================
echo.
echo Forwarding traffic to http://localhost:5173
echo Rewriting Host header so Vite accepts external requests.
echo.
echo Copy the "https://....trycloudflare.com" link generated below
echo and share it with your teammates!
echo Press Ctrl+C at any time to stop sharing.
echo ===================================================
echo.
cloudflared.exe tunnel --url http://localhost:5173 --http-host-header="localhost:5173"
pause
