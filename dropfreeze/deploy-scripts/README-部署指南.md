# Beads Ops Mobile 部署指南
# Amplify (前端) + EC2 跳板 + 本機 Flask

## 架構圖
```
手機瀏覽器
    ↓ HTTPS
Amplify Hosting (index.html + config.js)
    ↓ API 請求
EC2 t3.micro (Elastic IP + nginx)
    ↓ 反向 SSH 隧道
本機 Flask :5100 (存取本地 DB/NAS)
```

---

## Step 1: 開 EC2 跳板機

### 1.1 AWS Console → EC2 → Launch Instance
- Name: `beads-tunnel`
- AMI: **Amazon Linux 2023** (免費)
- Instance type: **t3.micro** (免費方案)
- Key pair: 建立新的，下載 `beads-ec2.pem`
  - 放到本機 `C:\Users\harryhrguo\.ssh\beads-ec2.pem`
- Security Group 開放:
  - **22** (SSH) - 來源: 你的公司 IP
  - **80** (HTTP) - 來源: 0.0.0.0/0
  - **443** (HTTPS) - 來源: 0.0.0.0/0

### 1.2 綁定 Elastic IP
- EC2 Console → Elastic IPs → Allocate
- 選擇剛建的 IP → Actions → Associate → 選 beads-tunnel
- **記下這個 IP，之後不會變**

### 1.3 SSH 進 EC2 執行初始化
```bash
# 本機 cmd (Windows)
ssh -i C:\Users\harryhrguo\.ssh\beads-ec2.pem ec2-user@<ELASTIC_IP>

# 進入 EC2 後
curl -O https://raw.githubusercontent.com/YOUR_REPO/ec2-setup.sh
# 或直接貼上 deploy-scripts/ec2-setup.sh 的內容執行
chmod +x ec2-setup.sh
./ec2-setup.sh
```

或手動執行：
```bash
# 安裝 nginx
sudo dnf install -y nginx
sudo systemctl enable nginx && sudo systemctl start nginx

# 允許反向隧道
sudo sed -i 's/^#GatewayPorts.*/GatewayPorts clientspecified/' /etc/ssh/sshd_config
grep -q "^GatewayPorts" /etc/ssh/sshd_config || echo "GatewayPorts clientspecified" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd

# nginx 設定
sudo tee /etc/nginx/conf.d/beads-api.conf > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    add_header Access-Control-Allow-Origin * always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Content-Type, Authorization" always;

    if ($request_method = OPTIONS) {
        return 204;
    }

    location / {
        proxy_pass http://127.0.0.1:5100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 20M;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

sudo nginx -t && sudo systemctl reload nginx
```

### 1.4 驗證 EC2
```bash
# 在 EC2 上測試 nginx 是否正常
curl http://localhost
# 應該回 502 (因為隧道還沒建)，這是正常的
```

---

## Step 2: 建立反向隧道 (本機 Windows)

### 2.1 第一次手動 SSH 確認 host key
```cmd
ssh -i C:\Users\harryhrguo\.ssh\beads-ec2.pem ec2-user@<ELASTIC_IP>
# 輸入 yes 接受 host key
# 確認能連上後 exit
```

### 2.2 修改 start_tunnel.bat
打開 `deploy-scripts\start_tunnel.bat`，修改：
```
SET EC2_IP=你的Elastic_IP
SET EC2_USER=ec2-user
SET EC2_KEY=C:\Users\harryhrguo\.ssh\beads-ec2.pem
```

### 2.3 啟動隧道
```cmd
# 先確認 Flask 在跑
python app_V13_W03.py

# 另開一個 cmd 視窗
deploy-scripts\start_tunnel.bat
```

### 2.4 驗證隧道
```bash
# 從外部測試 (手機或另一台電腦)
curl http://<ELASTIC_IP>/ping
# 應該回 {"ok": true, "msg": "pong"}
```

---

## Step 3: 部署前端到 Amplify

### 3.1 方法 A: 手動部署 (最簡單，不需 Git)

1. AWS Console → Amplify → Create new app
2. 選 **Deploy without Git provider**
3. App name: `beads-mobile`
4. Branch name: `main`
5. 把 `amplify-app` 資料夾壓成 ZIP：
   - 選取 amplify-app 裡的 **index.html**, **config.js**, **amplify.yml**
   - 右鍵 → 傳送到 → 壓縮的資料夾
6. 上傳 ZIP → Save and deploy
7. 部署完成後會得到 URL: `https://main.xxxxxxxxxx.amplifyapp.com`

### 3.2 方法 B: 用 AWS CLI 部署

```cmd
# 安裝 AWS CLI (如果還沒有)
# https://aws.amazon.com/cli/

# 設定 credentials
aws configure

# 建立 Amplify App
aws amplify create-app --name beads-mobile --platform WEB

# 記下回傳的 appId，例如 d1234abcde

# 建立 branch
aws amplify create-branch --app-id <APP_ID> --branch-name main

# 壓縮並部署
cd amplify-app
powershell Compress-Archive -Path * -DestinationPath ..\beads-deploy.zip -Force
cd ..

aws amplify start-deployment --app-id <APP_ID> --branch-name main --source-url s3://...
```

建議用方法 A，最快。

---

## Step 4: 更新 config.js 的 API_BASE

部署前，修改 `amplify-app/config.js`：

```javascript
window.API_BASE = "http://<你的ELASTIC_IP>";
```

然後重新上傳 ZIP 到 Amplify。

---

## Step 5: (選配) 加 HTTPS

### 5.1 如果有自己的域名
```bash
# SSH 進 EC2
sudo dnf install -y certbot python3-certbot-nginx

# 先把域名 A record 指向 Elastic IP
# 然後執行
sudo certbot --nginx -d api.beads.yourdomain.com

# certbot 會自動修改 nginx 設定加上 SSL
# 之後 config.js 改成
# window.API_BASE = "https://api.beads.yourdomain.com";
```

### 5.2 如果沒有域名
- HTTP 也能用，但手機瀏覽器可能會警告
- 建議買一個便宜域名 (~$10/年) 搭配 Let's Encrypt 免費 SSL

---

## 日常操作

### 每天開機後
1. 啟動 Flask: `python app_V13_W03.py`
2. 啟動隧道: 雙擊 `start_tunnel.bat`
3. 完成，手機可以用了

### 隧道斷線
- `start_tunnel.bat` 會自動重連 (5秒後)
- 如果持續斷線，檢查：
  - Flask 是否在跑
  - EC2 是否正常
  - 網路是否通

### 更新前端
1. 修改 `amplify-app/index.html`
2. 重新壓 ZIP 上傳到 Amplify Console
3. 30秒內生效

### 設為開機自動啟動 (選配)
把 `start_tunnel.bat` 的捷徑放到：
```
C:\Users\harryhrguo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
```

---

## 費用估算

| 項目 | 月費 |
|------|------|
| EC2 t3.micro (免費方案內) | $0 |
| EC2 t3.micro (超過免費期) | ~$8 |
| Elastic IP (綁定使用中) | $0 |
| Amplify Hosting (免費額度) | $0 |
| 域名 (選配) | ~$1/月 |
| **合計** | **$0 ~ $9/月** |

---

## 檔案清單

```
amplify-app/
├── index.html      ← 前端 (部署到 Amplify)
├── config.js       ← API 端點設定
└── amplify.yml     ← Amplify 建置設定

deploy-scripts/
├── ec2-setup.sh    ← EC2 初始化腳本
└── start_tunnel.bat ← 本機反向隧道啟動
```

---

## 故障排除

| 問題 | 檢查 |
|------|------|
| 手機打不開頁面 | Amplify URL 是否正確 |
| API 連不上 | `curl http://<IP>/ping` 測試 |
| 502 Bad Gateway | 隧道是否建立 / Flask 是否在跑 |
| CORS 錯誤 | nginx CORS header 是否設定 |
| 照片上傳失敗 | nginx client_max_body_size |
| 隧道一直斷 | 檢查 .pem 路徑 / EC2 安全群組 |
