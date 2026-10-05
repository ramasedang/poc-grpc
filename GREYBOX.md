# NusaKirim — Greybox Testing Package

Information provided to the tester for **greybox** assessment of the NusaKirim
shipping platform (gRPC / gRPC-Web target).

---

## 1. Targets & endpoints

| Surface | Address | Notes |
|---------|---------|-------|
| Web app (SPA) | `https://pocpoc.my.id:8181` | Browser client; all data via gRPC-Web |
| gRPC-Web | `https://pocpoc.my.id:8181/nusakirim.ShipmentService/<Method>` | `content-type: application/grpc-web+proto` |
| gRPC (plaintext) | `pocpoc.my.id:50051` (= `103.93.161.143:50051`) | **server reflection ON** |
| gRPC over TLS | `grpcs://pocpoc.my.id:50443` | Caddy terminates TLS → backend |

> **Access is IP-allowlisted.** The tester's source IP must be whitelisted first
> (operator runs `sudo lab-whitelist <IP>` on the VPS). SSH (22) is open to all.

## 2. Provided credentials (greybox)

| Username | Password | Role | Notes |
|----------|----------|------|-------|
| `ops` | `Ops#2024` | **staff** | operations / elevated account |
| `budi` | `budi123` | customer | owns AWB NK1001, NK1004 |
| `sari` | `sari123` | customer | owns AWB NK1002 |
| `andi` | `andi123` | customer | owns AWB NK1003 |

Sample tracking numbers (AWB): **NK1001 – NK1004**.
Passwords are stored server-side as unsalted MD5 (by design).

## 3. API schema

- Proto definition: `protos/shipping.proto` — service `nusakirim.ShipmentService`, 13 RPCs.
- **Reflection is enabled**, so the full schema is retrievable live:
  ```bash
  grpcurl -plaintext pocpoc.my.id:50051 list
  grpcurl -plaintext pocpoc.my.id:50051 describe nusakirim.ShipmentService
  ```
- RPCs: `Login, UpdateAccount, TrackShipment, SearchShipments, GetShipment,
  CancelShipment, DownloadDocument, FetchExternalTracking, ImportShipmentBatch,
  SubmitFeedback, ListFeedback, CheckHubConnectivity, RunMaintenance, SystemInfo,
  ResetDatabase`.

## 4. Auth model (for the tester)

- `Login` returns a JWT (`AuthResponse.token`).
- Some operations key off client-supplied metadata (e.g. header `x-role`) — in
  scope for authorization testing.

## 5. Example calls

```bash
# login
grpcurl -plaintext -d '{"username":"budi","password":"budi123"}' \
  pocpoc.my.id:50051 nusakirim.ShipmentService/Login

# tracking (public)
grpcurl -plaintext -d '{"tracking_no":"NK1001"}' \
  pocpoc.my.id:50051 nusakirim.ShipmentService/TrackShipment
```

## 6. Scope / rules of engagement

- In scope: the `nusakirim.ShipmentService` API and the web SPA on the listed ports.
- Out of scope: the host OS, SSH, other sites on the VPS, and the operator-only
  lab-reset control.
- Data may be mutated during testing; the operator can restore the seed state.

---

### Operator-only (NOT part of the tester package)

- Lab reset: SPA `#/reset` or RPC `ResetDatabase`, password via env
  `ADMIN_RESET_PASSWORD` (default `081Admin`). Used to restore seed data between runs.
