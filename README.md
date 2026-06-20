# Bleck Lous Voice Station

Web điều khiển bot voice đang chạy cùng process. Trang chính là giao diện vận hành Voice/RPC:

- Đăng nhập Discord OAuth2, không nhận user token.
- Chọn server và room để bot treo voice persistent.
- Lưu room đã ghim vào `archive_bot/data/voice_state.json`, tự nối lại sau disconnect, gateway reconnect hoặc service restart.
- Hiển thị room đang kết nối và room đang chờ reconnect.
- Admin web có thể đổi Presence/RPC chung của bot.
- User kích hoạt key cho server ngay trong mục `Quyền truy cập`.
- Admin panel riêng ở `/admin`, không dùng layout public; dùng để tạo/gia hạn/khóa key, xem user sử dụng key, ban/reset user, cấp quyền user/admin và xem yêu cầu nạp/thuê.
- Dữ liệu bot đọc SQLite hiện có ở chế độ read-only.
- Source archive cũ đã được ghép vào `archive_bot/`; `main.py` là file chính mới, chạy web dashboard và bot voice trong cùng process.

## Source archive đã tích hợp

Folder `archive_bot/` được nhập từ `/Users/hely-t/Downloads/archive-2026-02-12T215354+0100` và giữ nguyên các phần chính. Root `main.py` sẽ load cog từ folder này:

- `main.py`: entrypoint chính mới, start web từ `app.py`, rồi chạy bot nếu có token.
- `app.py`: module web Bleck Lous hiện tại, vẫn có thể chạy độc lập khi cần.
- `bot_runtime.py`: bridge thread-safe để web đọc trạng thái và điều khiển bot Discord đang chạy.
- `archive_bot/main.py`: entrypoint Discord cũ, giữ để tham khảo.
- `archive_bot/keep_alive.py`: Flask keep-alive mini server của source cũ.
- `archive_bot/cogs/voice.py`: join/leave voice, auto-reconnect, mic/speaker, voice status.
- `archive_bot/cogs/spam.py`: spam text, spam file, stop spam.
- `archive_bot/cogs/quotes.py`: auto quotes từ file data.
- `archive_bot/cogs/status.py`: dashboard trạng thái runtime của bot.
- `archive_bot/cogs/help.py`: help menu, quickhelp.
- `archive_bot/data/*.txt`: dữ liệu quotes/spam.

File `config.json` thật trong archive có token nên không được copy vào repo. Dùng `archive_bot/config.example.json` để tạo `archive_bot/config.json`, hoặc set `DISCORD_TOKEN`/`BOT_TOKEN` bằng systemd environment. `DISCORD_TOKEN` là Bot token từ Discord Developer Portal. Web điều khiển presence chung của bot; RPC cá nhân vẫn do từng người tự chạy riêng.

## Điều khiển bot trên web

Sau khi login Discord, vào `/control`:

- User có key còn hiệu lực được chọn server/phòng voice và treo hoặc rời room.
- User chỉ thấy server mình có quyền quản lý và đã kích hoạt key; admin web thấy các server mình quản lý.
- Role `admin` được đổi activity type, status, name, details, state và streaming URL của bot.
- Presence này là trạng thái của bot Discord dùng chung. Rich Presence cá nhân với application assets/image vẫn phải chạy riêng trên máy của từng người.
- Web không nhận và không lưu user token Discord.

## Chạy local

```bash
cd bleck-lous-web
cp .env.example .env
python3 app.py
```

Mở `http://localhost:8088`.

File chính mới:

```bash
python3 main.py
```

Nếu chưa cấu hình token bot, `main.py` chỉ chạy web. Nếu có token, nó sẽ chạy thêm bot voice và cho phép web đổi presence của bot. RPC cá nhân không chạy chung trong service này.

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
https://nasdaq-fx.com/admin
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
https://nasdaq-fx.com/auth/callback
```

3. Điền `.env`:

```env
DISCORD_CLIENT_ID=client_id_cua_app
DISCORD_CLIENT_SECRET=client_secret_cua_app
DISCORD_REDIRECT_URI=https://nasdaq-fx.com/auth/callback
CASINO_BOT_CLIENT_ID=client_id_bot_casino
GENERAL_BOT_CLIENT_ID=client_id_bot_tong
ADMIN_PASSWORD=mat_khau_admin_manh
CONTACT_ADMIN_URL=https://discord.gg/...
CASINO_SERVER_COUNT=0
GENERAL_SERVER_COUNT=0
```

`CASINO_BOT_CLIENT_ID` và `GENERAL_BOT_CLIENT_ID` là Application/Client ID của từng bot. Web tự tạo invite URL theo từng server user đang quản lý.

`DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` và redirect URL phải thuộc cùng một Discord Application. Nên dùng chính Application của voice bot cho cả OAuth và bot token để tránh cấu hình nhầm. Redirect URL trên Portal phải khớp tuyệt đối, kể cả `https`, domain và path. Source archive cũ không có web login; `config.json` của nó chỉ đăng nhập bot bằng token, nên Voice Station dùng OAuth2 chính thức cho người dùng web.

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
Environment=PUBLIC_DOMAIN=nasdaq-fx.com
Environment=HOST=127.0.0.1
Environment=PORT=8088
Environment=WEB_DB_PATH=/opt/discord-bots/main-bot/database/web-dashboard/web.sqlite3
Environment=DISCORD_CLIENT_ID=your_web_client_id
Environment=DISCORD_CLIENT_SECRET=your_web_client_secret
Environment=DISCORD_REDIRECT_URI=https://nasdaq-fx.com/auth/callback
Environment=CASINO_BOT_CLIENT_ID=casino_bot_client_id
Environment=GENERAL_BOT_CLIENT_ID=general_bot_client_id
Environment=ADMIN_PASSWORD=change_this_password
Environment=CONTACT_ADMIN_URL=https://discord.gg/your-support
Environment=CASINO_SERVER_COUNT=0
Environment=GENERAL_SERVER_COUNT=0
Environment=BOT_PREFIX=$
Environment=VOICE_STATE_PATH=/opt/bleck-lous-web/archive_bot/data/voice_state.json
# Optional. Leave empty/commented for web-only mode.
# Use the Bot token from Discord Developer Portal to run the voice bot too.
# Environment=DISCORD_TOKEN=your_bot_token
Environment=CASH_DB_PATH=/opt/discord-bots/main-bot/database/users.db
Environment=BANK_DB_PATH=/opt/discord-bots/main-bot/database/bank_payments.db
Environment=CASINO_DB_PATH=/opt/discord-bots/casino-bot/database/casino.db
ExecStart=/usr/bin/python3 /opt/bleck-lous-web/main.py
Restart=always
RestartSec=3
User=root
Group=root

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
    server_name nasdaq-fx.com www.nasdaq-fx.com;

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
sudo certbot --nginx -d nasdaq-fx.com -d www.nasdaq-fx.com
```

## Ghi chú database

- `CASH_DB_PATH`: file `users.db` của bot tổng Python, chứa `users.cash`, level, donate.
- `BANK_DB_PATH`: file `bank_payments.db`, chứa giao dịch nạp/donate và bảng donate.
- `CASINO_DB_PATH`: file casino Go, chứa `users.balance`, `transaction_logs`, `game_history`.

Web mở database bằng chế độ read-only, phù hợp để chạy chung VPS với bot.

Database riêng của web nên để chung khu database bot để dễ backup và mở bằng tool DB:

```text
/opt/discord-bots/main-bot/database/web-dashboard/web.sqlite3
```

Tạo folder trước khi chạy service:

```bash
sudo mkdir -p /opt/discord-bots/main-bot/database/web-dashboard
```

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
