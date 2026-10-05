# 🚚 NusaKirim — Vulnerable gRPC Shipping Target

A **deliberately vulnerable shipping/logistics application** for practicing
web & API penetration testing. Unlike DVWA, nothing in the UI is labelled
"SQL Injection" — every flaw is hidden inside an ordinary courier feature
(track a parcel, download an invoice, check hub connectivity, import a batch,
leave a review). Testers have to **discover** the bugs.

```
  browser ──HTTP──►  NusaKirim web portal (web.py)  ──gRPC──►  ShipmentService (server.py)
                     http://localhost:8000                     localhost:50051
```

Two attack surfaces, one SQLite DB: attack the **web portal** in a browser, or
hit the **gRPC service directly** with `grpcurl` (reflection is on).

> ⚠️ **Training only.** Contains RCE, SQLi, arbitrary file read, SSRF, etc.
> Run on an isolated/local machine. Never expose it to an untrusted network.

---

## OWASP Top 10 (2021) — operator map

> This table is for the lab operator. The portal UI shows none of it.

| Feature (looks legit) | RPC | Hidden weakness | OWASP |
|-----------------------|-----|-----------------|-------|
| Sign in | `Login` | No lockout/rate-limit, MD5 hashes, `alg:none` JWT accepted | A07 |
| Track parcel | `TrackShipment` | *(safe reference — parameterized)* | — |
| Search "my parcels" by recipient | `SearchShipments` | SQL injection (string-built query) | A03 |
| Parcel detail page | `GetShipment` | IDOR/BOLA — read any parcel's recipient PII | A01 |
| Cancel parcel | `CancelShipment` | No authorization check (destructive) | A01 |
| Account settings | `UpdateAccount` | Mass assignment — client sets its own `role` | A08 |
| Download invoice/label | `DownloadDocument` | Path traversal / arbitrary file read | A01 |
| "Track via partner courier" | `FetchExternalTracking` | SSRF (no allowlist/scheme check) | A10 |
| Bulk shipment import (.dat) | `ImportShipmentBatch` | Insecure deserialization (`pickle` RCE) | A08 |
| Hub connectivity diagnostic | `CheckHubConnectivity` | OS command injection (`shell=True`) | A03 |
| Maintenance task | `RunMaintenance` | Authz via spoofable `x-role` metadata + RCE | A01 |
| System status | `SystemInfo` + reflection | Secret/env disclosure, open reflection | A05 |
| Delivery review | `SubmitFeedback` | Stored XSS (web renders it unescaped) | — |
| Password storage | `customers.password` | Unsalted MD5 | A02 |

---

## Quick start

### Docker Compose (recommended)

Two services on an isolated bridge network — `backend` (gRPC) + `web` (Flask,
reaches the backend as `backend:50051`):

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

- Web portal → <http://localhost:8000>
- gRPC       → `grpcurl -plaintext localhost:50051 list`

| var | service | default | meaning |
|-----|---------|---------|---------|
| `GRPC_PORT` | backend | `50051` | backend listen port |
| `WEB_PORT` | web | `8000` | web listen port |
| `GRPC_TARGET` | web | `backend:50051` | where the web tier finds the backend |

### Local (venv)

```bash
make setup     # venv + deps + stubs + DB
make run       # backend :50051 + web :8000
```

---

## Accounts

| user | password | role | note |
|------|----------|------|------|
| ops | `Ops#2024` | staff | operations account |
| budi | `budi123` | customer | owns parcels NK1001, NK1004 |
| sari | `sari123` | customer | owns NK1002 |
| andi | `andi123` | customer | owns NK1003 |

Sample AWBs: `NK1001`–`NK1004`.

## Reset the lab (operator-only)

After an attack run mutates the data (cancelled parcels, escalated roles, XSS
in the guestbook), restore the original seed. This is a genuinely password-gated
control, **not** part of the attack surface.

- Hidden web page: <http://localhost:8000/__lab/reset> (not linked in the nav)
- Or via gRPC:
  ```bash
  grpcurl -plaintext -d '{"password":"081Admin"}' \
    localhost:50051 nusakirim.ShipmentService/ResetDatabase
  ```

Default password is `081Admin`; override with the `ADMIN_RESET_PASSWORD` env var
(it is scrubbed from the `SystemInfo` disclosure so it can't leak).

## Attacking the gRPC layer

Reflection is on, so `grpcurl` needs no proto file:

```bash
grpcurl -plaintext localhost:50051 list
grpcurl -plaintext localhost:50051 describe nusakirim.ShipmentService
```

See **[EXPLOITS.md](EXPLOITS.md)** for a payload per weakness.

## Layout

```
protos/shipping.proto   gRPC API (ShipmentService, 14 RPCs)
server.py               vulnerable gRPC backend
web.py                  Flask portal (realistic UI; also stored XSS)
database.py             SQLite schema + seed (customers, shipments, feedback)
security.py             broken JWT helpers
documents/              legit invoices/labels (path-traversal playground)
internal_ops.env        "internal" secrets reachable via traversal
EXPLOITS.md             grpcurl exploitation cheatsheet
```
