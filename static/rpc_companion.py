#!/usr/bin/env python3
"""Bleck Lous personal Rich Presence companion. Uses Discord Desktop IPC; never uses a user token."""

from __future__ import annotations

import argparse
import glob
import json
import os
import socket
import struct
import time
import urllib.request
import uuid


def ipc_paths() -> list[str]:
    roots = [os.getenv("TMPDIR", ""), "/tmp", "/var/tmp"]
    paths: list[str] = []
    for root in roots:
        if root:
            paths.extend(glob.glob(os.path.join(root, "discord-ipc-*")))
    return list(dict.fromkeys(paths))


def frame(opcode: int, payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<II", opcode, len(body)) + body


def receive(sock: socket.socket) -> dict:
    header = sock.recv(8)
    if len(header) != 8:
        raise ConnectionError("Discord IPC closed")
    _opcode, length = struct.unpack("<II", header)
    chunks = bytearray()
    while len(chunks) < length:
        chunk = sock.recv(length - len(chunks))
        if not chunk:
            raise ConnectionError("Discord IPC closed")
        chunks.extend(chunk)
    return json.loads(chunks.decode("utf-8"))


def connect_discord(client_id: str) -> socket.socket:
    last_error: Exception | None = None
    for path in ipc_paths():
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(8)
            sock.connect(path)
            sock.sendall(frame(0, {"v": 1, "client_id": str(client_id)}))
            ready = receive(sock)
            if ready.get("evt") != "READY":
                raise ConnectionError(str(ready))
            return sock
        except (OSError, ValueError, ConnectionError) as exc:
            last_error = exc
    raise ConnectionError(f"Không tìm thấy Discord Desktop IPC: {last_error or 'Discord chưa chạy'}")


def fetch_config(server: str, token: str) -> dict:
    request = urllib.request.Request(server.rstrip("/") + "/api/rpc/device")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("User-Agent", "BleckLousRPCCompanion/1.0")
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(payload.get("message", "RPC API error"))
    return payload


def activity(profile: dict) -> dict:
    types = {"playing": 0, "listening": 2, "watching": 3, "competing": 5}
    result = {
        "type": types.get(profile.get("activity_type"), 0),
        "details": profile.get("details") or None,
        "state": profile.get("state") or None,
        "timestamps": {"start": int(time.time())},
        "instance": False,
    }
    assets = {}
    if profile.get("large_image"):
        assets["large_image"] = profile["large_image"]
    if profile.get("large_text"):
        assets["large_text"] = profile["large_text"]
    if assets:
        result["assets"] = assets
    if profile.get("button_label") and profile.get("button_url"):
        result["buttons"] = [{"label": profile["button_label"], "url": profile["button_url"]}]
    return {key: value for key, value in result.items() if value is not None}


def update(sock: socket.socket, profile: dict) -> None:
    payload = {
        "cmd": "SET_ACTIVITY",
        "args": {"pid": os.getpid(), "activity": activity(profile)},
        "nonce": str(uuid.uuid4()),
    }
    sock.sendall(frame(1, payload))
    response = receive(sock)
    if response.get("evt") == "ERROR":
        raise RuntimeError(str(response.get("data", response)))


def run(server: str, token: str) -> None:
    sock: socket.socket | None = None
    current_client = ""
    last_profile = ""
    print("Bleck Lous RPC Companion đang chạy. Nhấn Ctrl+C để dừng.")
    while True:
        try:
            config = fetch_config(server, token)
            client_id = str(config.get("application_id", ""))
            if not client_id:
                raise RuntimeError("Server chưa cấu hình RPC_APPLICATION_ID")
            encoded = json.dumps(config.get("profile", {}), sort_keys=True)
            if sock is None or current_client != client_id:
                if sock:
                    sock.close()
                sock = connect_discord(client_id)
                current_client = client_id
                last_profile = ""
            if encoded != last_profile:
                update(sock, config["profile"])
                last_profile = encoded
                print("Đã cập nhật RPC cá nhân.")
            time.sleep(max(10, int(config.get("poll_seconds", 15))))
        except KeyboardInterrupt:
            if sock:
                try:
                    sock.sendall(frame(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": None}, "nonce": str(uuid.uuid4())}))
                except OSError:
                    pass
            print("\nĐã dừng RPC.")
            return
        except Exception as exc:
            print(f"RPC chưa sẵn sàng: {exc}. Thử lại sau 10 giây.")
            if sock:
                sock.close()
            sock = None
            time.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="https://nasdaq-fx.com")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    run(args.server, args.token)
