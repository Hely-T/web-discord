from flask import Flask
from threading import Thread
import os
import logging

# Tắt log của Flask để đỡ rối mắt trên console
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask('')

@app.route('/')
def home():
    return "<h1>I'm alive! Owo Farm is running.</h1>"

def run():
    # Tự động lấy Port từ cấu hình của Bot-Hosting.net
    # Nếu không tìm thấy (chạy local), nó sẽ dùng port 8080
    port = int(os.environ.get("SERVER_PORT", 8080))
    try:
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        print(f"❌ Webserver Error: {e}")

def keep_alive():
    t = Thread(target=run)
    t.start()