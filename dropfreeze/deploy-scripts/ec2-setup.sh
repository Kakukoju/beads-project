#!/bin/bash
# ============================================
# EC2 跳板機初始化腳本
# 用途：接收本機 autossh 反向隧道，nginx 反向代理到 HTTPS
# 
# 使用方式：
#   1. 開 EC2 t3.micro (Amazon Linux 2023 / Ubuntu 22.04)
#   2. 安全群組開放: 22(SSH), 80(HTTP), 443(HTTPS)
#   3. 綁定 Elastic IP
#   4. SSH 進去執行此腳本
# ============================================

set -e

echo "===== 1. 安裝 nginx + certbot ====="
# Amazon Linux 2023
if command -v dnf &> /dev/null; then
    sudo dnf install -y nginx certbot python3-certbot-nginx
    sudo systemctl enable nginx
    sudo systemctl start nginx
# Ubuntu
elif command -v apt &> /dev/null; then
    sudo apt update
    sudo apt install -y nginx certbot python3-certbot-nginx
    sudo systemctl enable nginx
    sudo systemctl start nginx
fi

echo "===== 2. 設定 SSH 允許反向隧道 ====="
# 確保 sshd 允許 GatewayPorts
sudo sed -i 's/^#GatewayPorts.*/GatewayPorts clientspecified/' /etc/ssh/sshd_config
sudo sed -i 's/^GatewayPorts.*/GatewayPorts clientspecified/' /etc/ssh/sshd_config
grep -q "^GatewayPorts" /etc/ssh/sshd_config || echo "GatewayPorts clientspecified" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd

echo "===== 3. 建立 nginx 設定 (HTTP 先用，之後加 HTTPS) ====="
# ★★★ 請將 YOUR_DOMAIN 替換為你的域名，或直接用 Elastic IP ★★★
# 如果沒有域名，先用 IP，certbot 步驟跳過

sudo tee /etc/nginx/conf.d/beads-api.conf > /dev/null << 'NGINX_CONF'
server {
    listen 80;
    server_name _;  # 改成你的域名，例: api.beads.example.com

    # CORS headers
    add_header Access-Control-Allow-Origin * always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Content-Type, Authorization" always;

    # 處理 preflight
    if ($request_method = OPTIONS) {
        return 204;
    }

    location / {
        proxy_pass http://127.0.0.1:5100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 上傳照片需要較大 body
        client_max_body_size 20M;

        # WebSocket (for SocketIO)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX_CONF

sudo nginx -t && sudo systemctl reload nginx

echo "===== 4. 完成 ====="
echo ""
echo "✅ EC2 跳板機設定完成！"
echo ""
echo "下一步："
echo "  1. 綁定 Elastic IP (如果還沒)"
echo "  2. 在本機執行 start_tunnel.bat 建立反向隧道"
echo "  3. 測試: curl http://<ELASTIC_IP>/ping"
echo ""
echo "如果有域名，執行以下加 HTTPS："
echo "  sudo certbot --nginx -d api.beads.example.com"
echo ""
