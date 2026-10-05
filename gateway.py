"""NusaKirim edge gateway — encrypted gRPC-Web <-> gRPC.

Mirrors the architecture of real apps (e.g. an `X-Encrypted-Request: 1` +
`application/grpc-web-text` front end): the browser sends a base64, AES-GCM
*encrypted* gRPC-Web body. This gateway decrypts it, forwards the inner
protobuf to the gRPC backend, then encrypts the response the same way.

So on the wire AND inside Burp/DevTools the body is ciphertext — to read or
tamper it a tester must recover the client-side AES key from app.js. That is
the intended POC: client-side encryption is obfuscation, not real protection.
"""
import base64
import os
import struct

import grpc
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import Flask, Response, request

# App-layer key. Deliberately also shipped in app.js (client-side) so the lab
# is solvable: find it in the JS, decrypt the captured payload.
KEY = bytes.fromhex(os.environ.get(
    "GRPCWEB_AES_KEY",
    "7b1e9c4af0d826135e7a9fbc0d4e8172a6c3b59d2f84e017c9a6b3d5e8f012a4"))
BACKEND = os.environ.get("GRPC_TARGET", "backend:50051")
PORT = int(os.environ.get("GATEWAY_PORT", "8080"))

app = Flask(__name__)
_channel = grpc.insecure_channel(BACKEND)

CORS = {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "POST,OPTIONS",
    "access-control-allow-headers": (
        "content-type,x-grpc-web,x-user-agent,x-encrypted-request,clientname,"
        "frontendip,activityid,x-trace-id,x-app-version,x-device-id,"
        "x-session-id,grpc-timeout,x-override,x-role,accept"),
    "access-control-expose-headers":
        "grpc-status,grpc-message,content-type,x-encrypted-response",
    "access-control-max-age": "7200",
}

# forwarded to the backend as gRPC metadata (the spoofable authz header lives here)
PASS_METADATA = ("x-role",)


def _decrypt(b64: bytes) -> bytes:
    raw = base64.b64decode(b64)
    return AESGCM(KEY).decrypt(raw[:12], raw[12:], None)


def _encrypt(data: bytes) -> bytes:
    iv = os.urandom(12)
    return base64.b64encode(iv + AESGCM(KEY).encrypt(iv, data, None))


def _frame(payload: bytes, flag: int = 0) -> bytes:
    return bytes([flag]) + struct.pack(">I", len(payload)) + payload


@app.route("/nusakirim.ShipmentService/<method>", methods=["POST", "OPTIONS"])
def rpc(method):
    if request.method == "OPTIONS":
        return Response(b"", headers=CORS)

    body = request.get_data()
    try:
        if request.headers.get("x-encrypted-request") == "1":
            raw = _decrypt(body)            # encrypted grpc-web-text
        else:
            raw = base64.b64decode(body)    # plain grpc-web-text fallback
    except Exception:
        return Response(b"bad request", status=400, headers=CORS)

    # inner gRPC-Web frame: [flag][len:4][protobuf]
    ln = struct.unpack(">I", raw[1:5])[0]
    proto = raw[5:5 + ln]

    md = [(h, request.headers.get(h)) for h in PASS_METADATA
          if request.headers.get(h) is not None]

    status, message, resp = 0, "", b""
    try:
        call = _channel.unary_unary(
            "/nusakirim.ShipmentService/" + method,
            request_serializer=lambda b: b,          # raw passthrough
            response_deserializer=lambda b: b)
        resp = call(proto, metadata=md, timeout=20)
    except grpc.RpcError as e:
        status = e.code().value[0]
        message = e.details() or ""

    out = b""
    if status == 0:
        out += _frame(resp, 0x00)                    # data frame
    out += _frame(("grpc-status:%d\r\ngrpc-message:%s\r\n"
                   % (status, message)).encode(), 0x80)   # trailer frame

    headers = dict(CORS)
    headers["content-type"] = "application/grpc-web-text"
    headers["x-encrypted-response"] = "1"
    return Response(_encrypt(out), headers=headers)


@app.get("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    print(f"[+] gateway on :{PORT} -> {BACKEND} (encrypted grpc-web-text)")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
