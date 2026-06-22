#!/usr/bin/env python3
"""Bleck Lous personal Rich Presence companion. Uses Discord Desktop IPC; never uses a user token."""

from __future__ import annotations

import argparse
import glob
import json
import os
import socket
import ssl
import struct
import time
import urllib.request
import uuid
from typing import BinaryIO


def tls_context() -> ssl.SSLContext:
    candidates: list[str] = []
    try:
        import certifi  # Included by the official python.org macOS installer.
        candidates.append(certifi.where())
    except ImportError:
        pass
    default_cafile = ssl.get_default_verify_paths().openssl_cafile
    if default_cafile:
        candidates.append(default_cafile)
    candidates.extend([
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
    ])
    for path in candidates:
        if path and os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


TLS_CONTEXT = tls_context()


def ipc_paths() -> list[str]:
    if os.name == "nt":
        return [rf"\\.\pipe\discord-ipc-{index}" for index in range(10)]
    roots = [os.getenv("TMPDIR", ""), "/tmp", "/var/tmp"]
    paths: list[str] = []
    for root in roots:
        if root:
            paths.extend(glob.glob(os.path.join(root, "discord-ipc-*")))
    return list(dict.fromkeys(paths))


def frame(opcode: int, payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<II", opcode, len(body)) + body


class IPCConnection:
    def __init__(self, transport: socket.socket | BinaryIO):
        self.transport = transport

    def sendall(self, data: bytes) -> None:
        if isinstance(self.transport, socket.socket):
            self.transport.sendall(data)
        else:
            self.transport.write(data)
            self.transport.flush()

    def recv(self, size: int) -> bytes:
        if isinstance(self.transport, socket.socket):
            return self.transport.recv(size)
        return self.transport.read(size)

    def close(self) -> None:
        self.transport.close()


def receive(sock: IPCConnection) -> dict:
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


def connect_discord(client_id: str) -> IPCConnection:
    last_error: Exception | None = None
    for path in ipc_paths():
        connection: IPCConnection | None = None
        try:
            if os.name == "nt":
                connection = IPCConnection(open(path, "r+b", buffering=0))
            else:
                unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                unix_socket.settimeout(8)
                unix_socket.connect(path)
                connection = IPCConnection(unix_socket)
            connection.sendall(frame(0, {"v": 1, "client_id": str(client_id)}))
            ready = receive(connection)
            if ready.get("evt") != "READY":
                raise ConnectionError(str(ready))
            return connection
        except (OSError, ValueError, ConnectionError) as exc:
            if connection:
                connection.close()
            last_error = exc
    raise ConnectionError(f"Không tìm thấy Discord Desktop IPC: {last_error or 'Discord chưa chạy'}")


def fetch_config(server: str, token: str) -> dict:
    request = urllib.request.Request(server.rstrip("/") + "/api/rpc/device")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("User-Agent", "BleckLousRPCCompanion/1.0")
    with urllib.request.urlopen(request, timeout=15, context=TLS_CONTEXT) as response:
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


def update(sock: IPCConnection, profile: dict) -> None:
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
    sock: IPCConnection | None = None
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
            try:
                time.sleep(10)
            except KeyboardInterrupt:
                print("\nĐã dừng RPC.")
                return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="https://nasdaq-fx.com")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    run(args.server, args.token)
