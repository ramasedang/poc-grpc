"""NusaKirim — customer & staff shipping portal (web tier).

A Flask front end that looks like an ordinary courier website. It talks to the
gRPC ShipmentService. The UI advertises no weaknesses; testers must find them.
(The web tier also renders feedback unescaped -> stored XSS.)
"""
import os

import grpc
from flask import (Flask, redirect, render_template_string, request, session,
                   url_for)
from markupsafe import Markup

import shipping_pb2 as pb
import shipping_pb2_grpc as pb_grpc

GRPC_TARGET = os.environ.get("GRPC_TARGET", "localhost:50051")
app = Flask(__name__)
app.secret_key = "nusakirim-portal-dev"   # weak, static session key


def stub():
    return pb_grpc.ShipmentServiceStub(grpc.insecure_channel(GRPC_TARGET))


BASE = """
<!doctype html><html lang=id><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>NusaKirim — Kirim Cepat ke Seluruh Nusantara</title>
<style>
 :root{--nk:#1d4ed8;--nk2:#f97316;--bg:#f1f5f9;--card:#fff;--tx:#0f172a;--mut:#64748b}
 *{box-sizing:border-box} body{margin:0;font-family:system-ui,Segoe UI,Arial;background:var(--bg);color:var(--tx)}
 header{background:var(--nk);color:#fff;padding:0 22px;display:flex;align-items:center;gap:22px;height:58px}
 header .logo{font-weight:800;font-size:20px;letter-spacing:.3px}
 header .logo span{color:var(--nk2)}
 header nav{display:flex;gap:4px;flex:1}
 header nav a{color:#dbeafe;text-decoration:none;padding:8px 12px;border-radius:8px;font-size:14px}
 header nav a:hover{background:rgba(255,255,255,.12);color:#fff}
 header .auth{font-size:13px;color:#bfdbfe}
 main{max-width:940px;margin:26px auto;padding:0 18px}
 h1{font-size:30px;margin:.2em 0} h2{margin-top:0}
 .card{background:var(--card);border:1px solid #e2e8f0;border-radius:14px;padding:20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}
 .hero{background:linear-gradient(120deg,#1d4ed8,#2563eb);color:#fff;border:0}
 .hero p{color:#dbeafe;max-width:560px}
 input,select,textarea{font:inherit;padding:11px 12px;border:1px solid #cbd5e1;border-radius:9px;width:100%;background:#fff;color:var(--tx)}
 label{display:block;font-size:13px;color:var(--mut);margin:10px 0 4px}
 .hero input{border:0}
 button{background:var(--nk2);color:#fff;border:0;padding:11px 20px;border-radius:9px;font-weight:600;cursor:pointer}
 button:hover{filter:brightness(1.05)}
 .row{display:flex;gap:10px;align-items:end;flex-wrap:wrap}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
 a.ship{display:block;text-decoration:none;color:inherit;border:1px solid #e2e8f0;border-radius:11px;padding:13px;background:#fff}
 a.ship:hover{border-color:var(--nk)}
 .badge{display:inline-block;font-size:11px;padding:2px 9px;border-radius:20px;background:#e0e7ff;color:#3730a3}
 .st{font-size:12px;color:var(--mut)}
 table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #e2e8f0;padding:9px 8px;text-align:left;font-size:14px}
 pre{background:#0f172a;color:#e2e8f0;padding:14px;border-radius:10px;overflow:auto;font-size:13px}
 .muted{color:var(--mut);font-size:13px} footer{color:var(--mut);text-align:center;font-size:12px;padding:26px}
 .stars{color:var(--nk2)}
</style></head><body>
<header>
 <div class="logo">Nusa<span>Kirim</span></div>
 <nav>
  <a href="/">Beranda</a>
  <a href="/track">Lacak</a>
  <a href="/dashboard">Kiriman Saya</a>
  <a href="/documents">Dokumen</a>
  <a href="/feedback">Ulasan</a>
  <a href="/account">Akun</a>
  <a href="/ops">Panel Ops</a>
 </nav>
 <div class="auth">{{ auth|safe }}</div>
</header>
<main>{{ body|safe }}</main>
<footer>© 2024 NusaKirim Logistics · Melayani 514 kota di Indonesia</footer>
</body></html>
"""


def page(body_html: str):
    if session.get("username"):
        auth = f"👤 {session['username']} · <a style='color:#fff' href='/logout'>keluar</a>"
    else:
        auth = "<a style='color:#fff' href='/login'>Masuk</a>"
    return render_template_string(BASE, body=Markup(body_html), auth=Markup(auth))


def _stars(n: int) -> str:
    n = max(0, min(5, int(n or 0)))
    return "★" * n + "☆" * (5 - n)


def _shipment_detail(s) -> str:
    return f"""
    <div class="card"><h2>Resi {s.tracking_no} <span class="badge">{s.status}</span></h2>
    <table>
      <tr><th>Pengirim</th><td>{s.sender_name}</td></tr>
      <tr><th>Penerima</th><td>{s.recipient_name}</td></tr>
      <tr><th>Alamat</th><td>{s.recipient_address}</td></tr>
      <tr><th>Telepon</th><td>{s.recipient_phone}</td></tr>
      <tr><th>Berat</th><td>{s.weight_kg} kg</td></tr>
      <tr><th>Biaya</th><td>Rp{s.cost:,}</td></tr>
      <tr><th>Catatan</th><td>{s.notes}</td></tr>
    </table></div>"""


# --------------------------------------------------------------------------- #

@app.route("/")
def home():
    return page("""
    <div class="card hero">
      <h1>Kirim cepat ke seluruh Nusantara 🚚</h1>
      <p>Lacak paket Anda secara real-time. Masukkan nomor resi untuk melihat status pengiriman.</p>
      <form action="/track" method="get" class="row" style="margin-top:14px">
        <div style="flex:1;min-width:220px"><input name="no" placeholder="Contoh: NK1001"></div>
        <button>Lacak</button>
      </form>
    </div>
    <div class="grid">
      <div class="card"><b>📦 Reguler</b><p class="muted">Estimasi 2–4 hari, terjangkau.</p></div>
      <div class="card"><b>⚡ Express</b><p class="muted">Sampai keesokan hari.</p></div>
      <div class="card"><b>💰 COD</b><p class="muted">Bayar di tempat, aman & mudah.</p></div>
    </div>""")


@app.route("/track", methods=["GET", "POST"])
def track():
    no = request.values.get("no", "").strip()
    result = ""
    if no:
        try:
            s = stub().TrackShipment(pb.TrackRequest(tracking_no=no))
            result = f"""
            <div class="card"><h2>Status resi {s.tracking_no}</h2>
            <p><span class="badge">{s.status}</span></p>
            <p class="muted">Penerima: {s.recipient_name} — {s.recipient_address}</p></div>"""
        except grpc.RpcError as e:
            result = f"<div class='card'>❌ {e.details()}</div>"
    return page(f"""
    <h1>Lacak Kiriman</h1>
    <div class="card"><form method="get" class="row">
      <div style="flex:1;min-width:220px"><label>Nomor Resi (AWB)</label>
      <input name="no" value="{no}" placeholder="NK1001"></div>
      <button>Lacak</button></form></div>{result}""")


@app.route("/login", methods=["GET", "POST"])
def login():
    msg = ""
    if request.method == "POST":
        r = stub().Login(pb.LoginRequest(
            username=request.form["username"], password=request.form["password"]))
        if r.ok:
            session.update(username=r.customer.username, uid=r.customer.id,
                           role=r.customer.role, full_name=r.customer.full_name,
                           token=r.token)
            return redirect(url_for("dashboard"))
        msg = f"<p style='color:#b91c1c'>{r.message}</p>"
    return page(f"""
    <h1>Masuk ke Akun</h1>
    <div class="card" style="max-width:420px">
      <form method="post">
        <label>Nama pengguna</label><input name="username" value="budi">
        <label>Kata sandi</label><input name="password" type="password" value="budi123">
        <div style="margin-top:14px"><button>Masuk</button></div>
        {msg}
      </form>
    </div>""")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    q = request.args.get("q", session.get("full_name", ""))
    rows = ""
    try:
        res = stub().SearchShipments(pb.SearchRequest(keyword=q))
        for s in res.shipments:
            rows += f"""
            <a class="ship" href="/shipment/{s.id}">
              <div class="badge">{s.status}</div>
              <div style="font-weight:700;margin-top:6px">{s.tracking_no}</div>
              <div class="st">→ {s.recipient_name}</div>
              <div class="st">Rp{s.cost:,} · {s.weight_kg} kg</div>
            </a>"""
    except grpc.RpcError as e:
        rows = f"<div class='card'>❌ {e.details()}</div>"
    return page(f"""
    <h1>Kiriman Saya</h1>
    <div class="card"><form method="get" class="row">
      <div style="flex:1;min-width:220px"><label>Cari berdasarkan nama penerima</label>
      <input name="q" value="{q}" placeholder="nama penerima"></div>
      <button>Cari</button></form></div>
    <div class="grid">{rows or '<p class=muted>Tidak ada kiriman.</p>'}</div>""")


@app.route("/shipment/<int:sid>")
def shipment(sid):
    try:
        s = stub().GetShipment(pb.ShipmentIdRequest(id=sid))
        return page(f"<a href='/dashboard' class='muted'>← kembali</a>{_shipment_detail(s)}")
    except grpc.RpcError as e:
        return page(f"<div class='card'>❌ {e.details()}</div>")


@app.route("/documents", methods=["GET", "POST"])
def documents():
    result = ""
    if request.method == "POST":
        fname = request.form.get("filename", "")
        r = stub().DownloadDocument(pb.DocumentRequest(filename=fname))
        result = f"<div class='card'><div class='muted'>{r.resolved_path}</div><pre>{r.content}</pre></div>"
    return page(f"""
    <h1>Dokumen Pengiriman</h1>
    <div class="card">
      <p class="muted">Unduh invoice, label, atau bukti pengiriman berdasarkan nama berkas.</p>
      <form method="post" class="row">
        <div style="flex:1;min-width:240px"><label>Nama berkas</label>
        <input name="filename" value="invoice_NK1001.txt"></div>
        <button>Unduh</button>
      </form>
      <p class="muted" style="margin-top:10px">Tersedia: invoice_NK1001.txt, label_NK1003.txt</p>
    </div>{result}""")


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        stub().SubmitFeedback(pb.FeedbackRequest(
            name=request.form.get("name", "anonim"),
            rating=int(request.form.get("rating", 5) or 5),
            comment=request.form.get("comment", "")))
        return redirect(url_for("feedback"))
    items = stub().ListFeedback(pb.Empty()).items
    # Comment rendered unescaped -> stored XSS.
    cards = "".join(
        f"<div class='card'><b>{i.name}</b> <span class='stars'>{_stars(i.rating)}</span>"
        f"<div style='margin-top:6px'>{i.comment}</div></div>" for i in items)
    return page(f"""
    <h1>Ulasan Pelanggan</h1>
    <div class="card">
      <form method="post">
        <div class="row">
          <div style="flex:1"><label>Nama</label><input name="name" value="Pelanggan"></div>
          <div style="width:120px"><label>Rating</label>
            <select name="rating"><option>5</option><option>4</option><option>3</option>
            <option>2</option><option>1</option></select></div>
        </div>
        <label>Ulasan Anda</label><textarea name="comment" rows="3"></textarea>
        <div style="margin-top:12px"><button>Kirim Ulasan</button></div>
      </form>
    </div>{cards}""")


@app.route("/account", methods=["GET", "POST"])
def account():
    if not session.get("uid"):
        return redirect(url_for("login"))
    saved = ""
    if request.method == "POST":
        c = stub().UpdateAccount(pb.UpdateAccountRequest(
            customer_id=session["uid"],
            email=request.form.get("email", ""),
            phone=request.form.get("phone", ""),
            address=request.form.get("address", ""),
            role=request.form.get("role", session.get("role", "customer"))))
        session["role"] = c.role
        saved = "<p style='color:#15803d'>Profil tersimpan.</p>"
    return page(f"""
    <h1>Pengaturan Akun</h1>
    <div class="card" style="max-width:520px">
      <form method="post">
        <label>Email</label><input name="email" value="{session.get('username','')}@mail.com">
        <label>Telepon</label><input name="phone" value="+628">
        <label>Alamat</label><input name="address" value="">
        <label>Tipe akun</label><input name="role" value="{session.get('role','customer')}">
        <div style="margin-top:14px"><button>Simpan</button></div>
        {saved}
      </form>
    </div>""")


@app.route("/ops", methods=["GET", "POST"])
def ops():
    out = ""
    action = request.form.get("action")
    if action == "hub":
        r = stub().CheckHubConnectivity(pb.HubRequest(hub_host=request.form.get("host", "")))
        out = f"<div class='card'><div class='muted'>{r.command}</div><pre>{r.output}</pre></div>"
    elif action == "partner":
        r = stub().FetchExternalTracking(pb.UrlRequest(url=request.form.get("url", "")))
        out = f"<div class='card'>HTTP {r.status}<pre>{r.body}</pre></div>"
    elif action == "sysinfo":
        r = stub().SystemInfo(pb.Empty())
        env = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in sorted(r.environment.items()))
        out = f"""<div class='card'>versi: {r.version}<br>signing key: <code>{r.signing_key}</code>
        <table><tr><th>ENV</th><th>value</th></tr>{env}</table></div>"""
    return page(f"""
    <h1>Panel Operasional</h1>
    <div class="card">
      <h2>Diagnostik Konektivitas Hub</h2>
      <p class="muted">Cek koneksi jaringan ke hub/cabang.</p>
      <form method="post" class="row">
        <input type="hidden" name="action" value="hub">
        <div style="flex:1;min-width:220px"><input name="host" value="hub-bandung.local"></div>
        <button>Cek</button></form>
    </div>
    <div class="card">
      <h2>Lacak via Mitra Kurir</h2>
      <p class="muted">Ambil status dari endpoint mitra (JNE/J&amp;T/SiCepat).</p>
      <form method="post" class="row">
        <input type="hidden" name="action" value="partner">
        <div style="flex:1;min-width:220px"><input name="url" value="http://partner.local/track"></div>
        <button>Ambil</button></form>
    </div>
    <div class="card">
      <h2>Status Sistem</h2>
      <form method="post"><input type="hidden" name="action" value="sysinfo">
      <button>Tampilkan</button></form>
    </div>{out}""")


# Hidden operator-only lab reset (not linked in the nav). The password is
# checked by the backend, not here, so the web tier never stores it.
@app.route("/__lab/reset", methods=["GET", "POST"])
def lab_reset():
    msg = ""
    if request.method == "POST":
        try:
            r = stub().ResetDatabase(pb.ResetRequest(password=request.form.get("password", "")))
            msg = f"<p style='color:#15803d'>✅ {r.message}</p>"
        except grpc.RpcError as e:
            msg = f"<p style='color:#b91c1c'>❌ {e.details()}</p>"
    return page(f"""
    <h1>🔧 Lab Control</h1>
    <div class="card" style="max-width:420px">
      <p class="muted">Kembalikan data target (kiriman, akun, ulasan) ke kondisi awal.</p>
      <form method="post">
        <label>Password operator</label>
        <input name="password" type="password" autofocus>
        <div style="margin-top:14px"><button>Reset Database</button></div>
        {msg}
      </form>
    </div>""")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "8000")), debug=True)
