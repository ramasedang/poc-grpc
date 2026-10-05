"""NusaKirim ShipmentService — gRPC backend.

A realistic-looking shipping API. Each method implements an ordinary feature
(tracking, invoices, hub diagnostics, batch import, reviews) but hides a
security flaw inside that business logic. OWASP mapping is in README/EXPLOITS.

Training target — do not run on an untrusted network.
"""
import hmac
import os
import pickle
import subprocess
from concurrent import futures

import grpc
import requests
from grpc_reflection.v1alpha import reflection

import database
import security
import shipping_pb2 as pb
import shipping_pb2_grpc as pb_grpc

HERE = os.path.dirname(__file__)
DOCS_DIR = os.path.join(HERE, "documents")

# Operator-only lab reset password (change via env, defaults to 081Admin).
RESET_PASSWORD = os.environ.get("ADMIN_RESET_PASSWORD", "081Admin")


class ShipmentServicer(pb_grpc.ShipmentServiceServicer):
    # -- Login (weak hashing, no lockout/rate-limit; alg:none JWT accepted) ----
    def Login(self, request, context):
        conn = database.connect()
        row = conn.execute(
            "SELECT * FROM customers WHERE username = ? AND password = ?",
            (request.username, database.md5(request.password)),
        ).fetchone()
        conn.close()
        if not row:
            return pb.AuthResponse(ok=False, message="username atau kata sandi salah")
        c = dict(row)
        return pb.AuthResponse(
            ok=True, token=security.issue_token(c), message="ok", customer=_to_customer(c)
        )

    # -- Public tracking (parameterized; the "safe" reference feature) ---------
    def TrackShipment(self, request, context):
        conn = database.connect()
        row = conn.execute(
            "SELECT * FROM shipments WHERE tracking_no = ?", (request.tracking_no,)
        ).fetchone()
        conn.close()
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "nomor resi tidak ditemukan")
        return _to_shipment(dict(row))

    # -- Staff recipient search -> SQL injection -------------------------------
    def SearchShipments(self, request, context):
        # Recipient keyword is concatenated straight into SQL.
        sql = (
            "SELECT * FROM shipments "
            f"WHERE recipient_name LIKE '%{request.keyword}%' ORDER BY id"
        )
        conn = database.connect()
        try:
            rows = conn.execute(sql).fetchall()
        except Exception as e:
            conn.close()
            context.abort(grpc.StatusCode.INTERNAL, f"query error: {e} | sql: {sql}")
        conn.close()
        return pb.ShipmentList(
            shipments=[_to_shipment(dict(r)) for r in rows], debug_query=sql
        )

    # -- Shipment detail by id -> IDOR / BOLA (no ownership check) --------------
    def GetShipment(self, request, context):
        conn = database.connect()
        row = conn.execute("SELECT * FROM shipments WHERE id = ?", (request.id,)).fetchone()
        conn.close()
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "kiriman tidak ditemukan")
        return _to_shipment(dict(row))   # returns anyone's recipient PII

    # -- Cancel shipment -> missing authorization (destructive, unauth) --------
    def CancelShipment(self, request, context):
        conn = database.connect()
        conn.execute("UPDATE shipments SET status='Cancelled' WHERE id=?", (request.id,))
        conn.commit()
        conn.close()
        return pb.StatusResponse(ok=True, message=f"kiriman #{request.id} dibatalkan")

    # -- Update account -> mass assignment (client sets its own role) ----------
    def UpdateAccount(self, request, context):
        conn = database.connect()
        conn.execute(
            "UPDATE customers SET email=?, phone=?, address=?, role=? WHERE id=?",
            (request.email, request.phone, request.address, request.role, request.customer_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (request.customer_id,)
        ).fetchone()
        conn.close()
        return _to_customer(dict(row))

    # -- Download invoice/label/POD -> path traversal --------------------------
    def DownloadDocument(self, request, context):
        # Filenames are expected relative to documents/, but not sandboxed.
        full = os.path.join(DOCS_DIR, request.filename)
        try:
            with open(full, "r", errors="replace") as f:
                content = f.read()
        except Exception as e:
            content = f"error: {e}"
        return pb.DocumentResponse(content=content, resolved_path=os.path.abspath(full))

    # -- Partner-courier tracking lookup -> SSRF -------------------------------
    def FetchExternalTracking(self, request, context):
        try:
            r = requests.get(request.url, timeout=5)  # no allowlist / scheme check
            return pb.FetchResponse(status=r.status_code, body=r.text[:4000])
        except Exception as e:
            return pb.FetchResponse(status=0, body=f"error: {e}")

    # -- Bulk shipment import -> insecure deserialization (pickle RCE) ----------
    def ImportShipmentBatch(self, request, context):
        data = pickle.loads(request.batch)
        n = len(data) if hasattr(data, "__len__") else 1
        return pb.ImportResponse(result=f"batch diproses: {data!r}", imported=n)

    # -- Delivery feedback -> stored XSS (rendered unescaped by web tier) -------
    def SubmitFeedback(self, request, context):
        conn = database.connect()
        conn.execute(
            "INSERT INTO feedback (name, rating, comment) VALUES (?, ?, ?)",
            (request.name, request.rating, request.comment),
        )
        conn.commit()
        conn.close()
        return self.ListFeedback(pb.Empty(), context)

    def ListFeedback(self, request, context):
        conn = database.connect()
        rows = conn.execute("SELECT name, rating, comment FROM feedback ORDER BY id").fetchall()
        conn.close()
        return pb.FeedbackList(items=[
            pb.Feedback(name=r["name"], rating=r["rating"], comment=r["comment"]) for r in rows
        ])

    # -- Hub connectivity diagnostic -> OS command injection -------------------
    def CheckHubConnectivity(self, request, context):
        cmd = f"ping -c 2 {request.hub_host}"          # shell=True + raw input
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return pb.DiagnosticResponse(
            output=proc.stdout + proc.stderr, exit_code=proc.returncode, command=cmd
        )

    # -- Maintenance task -> authz via spoofable metadata + command exec -------
    def RunMaintenance(self, request, context):
        md = dict(context.invocation_metadata())
        # "role" comes from a client-supplied header we trust blindly.
        if md.get("x-role") != "staff":
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "khusus staff")
        proc = subprocess.run(request.task, shell=True, capture_output=True, text=True)
        return pb.DiagnosticResponse(
            output=proc.stdout + proc.stderr, exit_code=proc.returncode, command=request.task
        )

    # -- System info -> secret/env disclosure ----------------------------------
    def SystemInfo(self, request, context):
        # Leak the environment (intentional A05) -- but never the operator's
        # lab-reset password, so resetting the target stays operator-only.
        env = {k: v for k, v in os.environ.items() if k != "ADMIN_RESET_PASSWORD"}
        return pb.SystemInfoResponse(
            environment=env,
            signing_key=security.JWT_SECRET,
            version="nusakirim-api 1.0",
        )

    # -- Operator-only: restore the lab to its seed state ----------------------
    def ResetDatabase(self, request, context):
        # Constant-time check so this control is genuinely gated (unlike the
        # deliberately-broken auth used elsewhere in the target).
        if not hmac.compare_digest(request.password or "", RESET_PASSWORD):
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "password salah")
        database.init_db(force=True)   # drop + reseed customers/shipments/feedback
        return pb.StatusResponse(ok=True, message="database dikembalikan ke kondisi awal")


def _to_customer(d: dict) -> "pb.Customer":
    return pb.Customer(
        id=d.get("id", 0), username=d.get("username", ""), email=d.get("email", ""),
        role=d.get("role", ""), full_name=d.get("full_name", ""),
        phone=d.get("phone", ""), address=d.get("address", ""),
    )


def _to_shipment(d: dict) -> "pb.Shipment":
    return pb.Shipment(
        id=d.get("id", 0), tracking_no=d.get("tracking_no", ""),
        sender_name=d.get("sender_name", ""), recipient_name=d.get("recipient_name", ""),
        recipient_address=d.get("recipient_address", ""), recipient_phone=d.get("recipient_phone", ""),
        weight_kg=d.get("weight_kg", 0.0) or 0.0, status=d.get("status", ""),
        cost=d.get("cost", 0) or 0, notes=d.get("notes", ""), owner_id=d.get("owner_id", 0) or 0,
    )


def serve(port: int = 50051) -> None:
    database.init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb_grpc.add_ShipmentServiceServicer_to_server(ShipmentServicer(), server)
    # Server reflection left ON (misconfig): the whole API is enumerable.
    reflection.enable_server_reflection(
        (pb.DESCRIPTOR.services_by_name["ShipmentService"].full_name, reflection.SERVICE_NAME),
        server,
    )
    server.add_insecure_port(f"[::]:{port}")     # plaintext, no TLS
    server.start()
    print(f"[+] NusaKirim ShipmentService listening on 0.0.0.0:{port} (plaintext)")
    server.wait_for_termination()


if __name__ == "__main__":
    serve(int(os.environ.get("GRPC_PORT", "50051")))
