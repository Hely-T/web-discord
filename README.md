# Bleck Lous Web

Web public kiểu Jockie cho 2 bot Discord hiện có. Trang ngoài chỉ là hero + invite:

- Invite bot casino: public, bấm là mời bot.
- Invite bot tổng: phải nhập key hợp lệ rồi mới mở link invite.
- Dashboard: bấm là bắt login Discord, lưu user vào `web.sqlite3`, sau đó mới thấy server, nạp tiền thủ công, thuê key, kích hoạt key.
- Status: hiển thị bot đang operational hay không, số server, số user và uptime.
- Admin panel riêng ở `/admin`, không dùng layout public; dùng để tạo/gia hạn/khóa key, xem user sử dụng key, ban/reset user, cấp quyền user/admin và xem yêu cầu nạp/thuê.
- Dữ liệu bot đọc SQLite hiện có ở chế độ read-only.

## Chạy local

```bash
cd bleck-lous-web
cp .env.example .env
python3 app.py
```

Mở `http://localhost:8088`.

Nếu chạy trên máy đang có source bot:

```bash
CASH_DB_PATH="/Users/hely-t/Desktop/BOT DISCORD/database/users.db" \
BANK_DB_PATH="/Users/hely-t/Desktop/BOT DISCORD/database/bank_payments.db" \
CASINO_DB_PATH="/Users/hely-t/Desktop/CASINO/database/casino.db" \
python3 app.py
```

Muốn test admin local:

```bash
ADMIN_PASSWORD=123456 python3 app.py
```

Vào `http://localhost:8088/admin`, nhập mật khẩu, tạo key, sau đó login Discord và nhập key ở server muốn dùng bot tổng.

## Admin panel

Đường dẫn:

```text
https://nadnasdaq-fx.com/admin
```

Chức năng hiện có:

- Tạo key theo số ngày sử dụng (`duration_days`) và giới hạn số server.
- Xem hạn key, trạng thái key, số server đã dùng và user/server đang sử dụng.
- Khóa key, mở lại key, gia hạn thêm 30 ngày.
- Xem user đã login web.
- Ban/unban user khỏi web.
- Reset user: xóa key claim, yêu cầu nạp/thuê và server đã lưu của user.
- Cấp quyền `user` hoặc `admin` cho user trong database web.
- Xem yêu cầu nạp tiền và thuê key.

## Cấu hình Discord OAuth

Trong Discord Developer Portal của web/app chính:

1. Vào **OAuth2**.
2. Thêm redirect URL:

```text
https://nadnasdaq-fx.com/auth/callback
```

3. Điền `.env`:

```env
DISCORD_CLIENT_ID=client_id_cua_app
DISCORD_CLIENT_SECRET=client_secret_cua_app
DISCORD_REDIRECT_URI=https://nadnasdaq-fx.com/auth/callback
CASINO_BOT_CLIENT_ID=client_id_bot_casino
GENERAL_BOT_CLIENT_ID=client_id_bot_tong
ADMIN_PASSWORD=mat_khau_admin_manh
CONTACT_ADMIN_URL=https://discord.gg/...
CASINO_SERVER_COUNT=0
GENERAL_SERVER_COUNT=0
```

`CASINO_BOT_CLIENT_ID` và `GENERAL_BOT_CLIENT_ID` là Application/Client ID của từng bot. Web tự tạo invite URL theo từng server user đang quản lý.

Nếu sau này bot ghi được số server thật vào API/database thì có thể thay phần status. Hiện tại web dùng `GENERAL_SERVER_COUNT`, `CASINO_SERVER_COUNT`; bot tổng còn có số server đã kích hoạt key làm fallback.

## Deploy Ubuntu 22.04

Copy thư mục này lên VPS, ví dụ `/opt/bleck-lous-web`, rồi tạo file `/etc/systemd/system/bleck-lous-web.service`:

```ini
[Unit]
Description=Bleck Lous public web
After=network.target

[Service]
WorkingDirectory=/opt/bleck-lous-web
Environment=APP_BRAND=Bleck Lous
Environment=PUBLIC_DOMAIN=nadnasdaq-fx.com
Environment=HOST=127.0.0.1
Environment=PORT=8088
Environment=WEB_DB_PATH=/opt/bleck-lous-web/web.sqlite3
Environment=DISCORD_CLIENT_ID=your_web_client_id
Environment=DISCORD_CLIENT_SECRET=your_web_client_secret
Environment=DISCORD_REDIRECT_URI=https://nadnasdaq-fx.com/auth/callback
Environment=CASINO_BOT_CLIENT_ID=casino_bot_client_id
Environment=GENERAL_BOT_CLIENT_ID=general_bot_client_id
Environment=ADMIN_PASSWORD=change_this_password
Environment=CONTACT_ADMIN_URL=https://discord.gg/your-support
Environment=CASINO_SERVER_COUNT=0
Environment=GENERAL_SERVER_COUNT=0
Environment=CASH_DB_PATH=/opt/bot-discord/database/users.db
Environment=BANK_DB_PATH=/opt/bot-discord/database/bank_payments.db
Environment=CASINO_DB_PATH=/opt/casino/database/casino.db
ExecStart=/usr/bin/python3 /opt/bleck-lous-web/app.py
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bleck-lous-web
sudo systemctl status bleck-lous-web
```

Nginx reverse proxy:

```nginx
server {
    listen 80;
    server_name nadnasdaq-fx.com www.nadnasdaq-fx.com;

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Sau đó bật HTTPS:

```bash
sudo certbot --nginx -d nadnasdaq-fx.com -d www.nadnasdaq-fx.com
```

## Ghi chú database

- `CASH_DB_PATH`: file `users.db` của bot tổng Python, chứa `users.cash`, level, donate.
- `BANK_DB_PATH`: file `bank_payments.db`, chứa giao dịch nạp/donate và bảng donate.
- `CASINO_DB_PATH`: file casino Go, chứa `users.balance`, `transaction_logs`, `game_history`.

Web mở database bằng chế độ read-only, phù hợp để chạy chung VPS với bot.

## Push GitHub

Nếu thư mục `bleck-lous-web` chưa là git repo:

```bash
cd /Users/hely-t/Documents/web/bleck-lous-web
git init
git add .
git commit -m "Initial Bleck Lous web portal"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

Nếu repo đã có sẵn:

```bash
cd /Users/hely-t/Documents/web/bleck-lous-web
git status
git add .
git commit -m "Update admin panel and license management"
git push
```

Không push `.env`, `web.sqlite3`, file `.db` vì đã có `.gitignore`.

## Update lên VPS từ GitHub

Lần đầu trên VPS:

```bash
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/<username>/<repo>.git bleck-lous-web
sudo chown -R www-data:www-data /opt/bleck-lous-web
```

Tạo service systemd như phần deploy ở trên, rồi:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bleck-lous-web
```

Các lần update sau:

```bash
cd /opt/bleck-lous-web
sudo git pull
sudo systemctl restart bleck-lous-web
sudo systemctl status bleck-lous-web
```

Kiểm log nếu lỗi:

```bash
sudo journalctl -u bleck-lous-web -n 100 --no-pager
```
