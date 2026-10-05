# Functional Requirements Document (FRD)
## Platform Pengiriman — NusaKirim

### Kontrol Dokumen
| Versi | Tanggal | Penulis | Status |
|---|---|---|---|
| 1.0 | 2026-09-27 | Tim Produk NusaKirim | Approved |

---

## 1. Pendahuluan

### 1.1 Tujuan
Dokumen ini mendefinisikan kebutuhan fungsional dan non-fungsional untuk platform
pengiriman paket **NusaKirim**, mencakup portal pelanggan, pelacakan kiriman,
manajemen kiriman, dokumen pengiriman, integrasi mitra kurir, ulasan pelanggan,
dan konsol operasional. Dokumen menjadi acuan bersama bagi tim produk,
pengembang, QA, dan operasional.

### 1.2 Ruang Lingkup
Rilis ini mencakup layanan inti backend (`ShipmentService`), gateway API, dan
aplikasi web (SPA). Modul di luar ruang lingkup rilis ini: pembayaran online,
manajemen armada/kurir, dan aplikasi mobile native.

### 1.3 Definisi & Istilah
| Istilah | Keterangan |
|---|---|
| AWB / Resi | Nomor unik pelacakan kiriman (mis. `NK1001`) |
| Pelanggan | Pengguna yang membuat/menerima kiriman |
| Staff | Pengguna operasional internal |
| SPA | Single Page Application (aplikasi web sisi browser) |
| gRPC / gRPC-Web | Protokol antarmuka layanan; gRPC-Web dipakai dari browser |

### 1.4 Referensi
- Kontrak API terperinci: berkas **`shipping.proto`** (definisi `nusakirim.ShipmentService`).
- Skema basis data seed: Lampiran A.

---

## 2. Gambaran Produk

### 2.1 Latar Belakang
NusaKirim adalah layanan pengiriman paket antarkota. Pelanggan dapat melacak
paket, mengelola akun, mengunduh dokumen pengiriman, dan memberi ulasan. Staff
operasional memiliki fitur pencarian kiriman dan diagnostik jaringan hub.

### 2.2 Tujuan Bisnis
- Memberi pelanggan visibilitas status kiriman secara real-time.
- Menyediakan tim operasional alat bantu pencarian dan diagnostik.
- Menyediakan API terstruktur (gRPC) yang dapat dikonsumsi berbagai kanal.

### 2.3 Pengguna & Peran
| Peran | Deskripsi | Contoh hak akses |
|---|---|---|
| Anonim | Pengunjung belum login | Lacak resi publik, kirim ulasan |
| Pelanggan (`customer`) | Pemilik akun | Kelola akun sendiri, lihat kiriman miliknya |
| Staff (`staff`) | Operasional internal | Cari kiriman, konsol operasional |

---

## 3. Arsitektur Sistem

Aplikasi web bersifat SPA yang memanggil layanan gRPC melalui gRPC-Web.

```
  Browser (SPA) ──HTTPS──► API Gateway (Caddy) ──► gRPC-Web Proxy (Envoy) ──► ShipmentService (gRPC) ──► Basis data (SQLite)
```

### 3.1 Komponen & Teknologi
| Komponen | Teknologi | Peran |
|---|---|---|
| Frontend | HTML + JavaScript (SPA) | Antarmuka pengguna, memanggil API via gRPC-Web |
| API Gateway | Caddy 2 | Terminasi TLS, penyajian aset statis, routing API |
| gRPC-Web Proxy | Envoy | Menerjemahkan gRPC-Web ⇄ gRPC |
| Layanan Backend | Python + grpcio | Logika bisnis `ShipmentService` |
| Basis Data | SQLite | Data pelanggan, kiriman, ulasan |
| Autentikasi | JWT | Token sesi diterbitkan saat login |

### 3.2 Antarmuka Eksternal
| Antarmuka | Alamat | Keterangan |
|---|---|---|
| Portal Web | `https://pocpoc.my.id:8181/` | Aplikasi web SPA |
| API gRPC-Web | `https://pocpoc.my.id:8181/nusakirim.ShipmentService/<Method>` | Dipakai oleh SPA |
| API gRPC (TLS) | `grpcs://pocpoc.my.id:50443` | Konsumsi layanan via TLS |
| API gRPC | `pocpoc.my.id:50051` | Konsumsi layanan (plaintext) |

---

## 4. Kebutuhan Fungsional

Setiap kebutuhan mencantumkan aktor, input/output, aturan bisnis, dan kriteria
penerimaan (acceptance criteria).

### 4.1 Modul A — Akun & Autentikasi

**FR-A1 — Login**
- Aktor: Anonim.
- Operasi: `Login(username, password)`.
- Output: token sesi (JWT) + profil pelanggan bila kredensial valid.
- Aturan bisnis: kredensial tidak valid ditolak tanpa membocorkan field mana yang salah.
- Kriteria penerimaan: kredensial benar → token + profil; salah → pesan generik "kredensial tidak valid".

**FR-A2 — Kelola Akun**
- Aktor: Pelanggan terautentikasi.
- Operasi: `UpdateAccount(...)`.
- Fungsi: pelanggan memperbarui `email`, `phone`, `address` **miliknya sendiri**.
- Aturan bisnis: pelanggan tidak dapat mengubah tipe akun/peran; tidak dapat mengubah akun milik orang lain.
- Kriteria penerimaan: perubahan data kontak tersimpan; peran akun tidak berubah oleh aksi pelanggan.

### 4.2 Modul B — Pelacakan

**FR-B1 — Lacak Resi (Publik)**
- Aktor: Anonim.
- Operasi: `TrackShipment(tracking_no)`.
- Output: status pengiriman untuk resi yang valid.
- Aturan bisnis: pelacakan publik menampilkan informasi tingkat status; resi tidak dikenal → pesan "tidak ditemukan".

### 4.3 Modul C — Manajemen Kiriman

**FR-C1 — Cari Kiriman**
- Aktor: Staff.
- Operasi: `SearchShipments(keyword)`.
- Fungsi: mencari kiriman berdasarkan nama penerima.
- Aturan bisnis: fitur diperuntukkan bagi staff; input pencarian diproses secara aman.

**FR-C2 — Detail Kiriman**
- Aktor: Pelanggan (pemilik) / Staff.
- Operasi: `GetShipment(id)`.
- Output: detail kiriman termasuk data penerima.
- Aturan bisnis: pelanggan hanya dapat melihat kiriman **miliknya**; akses ke kiriman milik pihak lain ditolak.

**FR-C3 — Batalkan Kiriman**
- Aktor: Pemilik / Staff.
- Operasi: `CancelShipment(id)`.
- Fungsi: menandai kiriman berstatus dibatalkan.
- Aturan bisnis: hanya pemilik kiriman atau staff yang berhak; operasi memerlukan autentikasi & otorisasi.

### 4.4 Modul D — Dokumen

**FR-D1 — Unduh Dokumen**
- Aktor: Pengguna terautentikasi.
- Operasi: `DownloadDocument(filename)`.
- Output: berkas invoice / label / bukti kirim.
- Aturan bisnis: akses berkas dibatasi pada direktori dokumen resmi; nama berkas divalidasi.

### 4.5 Modul E — Integrasi Mitra

**FR-E1 — Lacak via Mitra Kurir**
- Aktor: Staff.
- Operasi: `FetchExternalTracking(url)`.
- Fungsi: mengambil status dari endpoint mitra kurir yang disetujui.
- Aturan bisnis: hanya host/skema mitra yang di-allowlist yang boleh diakses.

**FR-E2 — Impor Batch Kiriman**
- Aktor: Staff.
- Operasi: `ImportShipmentBatch(batch)`.
- Fungsi: mengimpor sekumpulan kiriman dari berkas unggahan.
- Aturan bisnis: format impor menggunakan format data yang aman dan terdefinisi.

### 4.6 Modul F — Ulasan

**FR-F1 — Kirim Ulasan**
- Aktor: Pengguna.
- Operasi: `SubmitFeedback(name, rating, comment)`.
- Fungsi: menyimpan ulasan pengiriman (rating 1–5).

**FR-F2 — Daftar Ulasan**
- Aktor: Pengguna.
- Operasi: `ListFeedback()`.
- Output: daftar ulasan yang ditampilkan di portal.
- Aturan bisnis: konten ulasan dari pengguna ditampilkan secara aman di antarmuka.

### 4.7 Modul G — Konsol Operasional (Staff)

**FR-G1 — Diagnostik Konektivitas Hub**
- Aktor: Staff.
- Operasi: `CheckHubConnectivity(hub_host)`.
- Fungsi: memeriksa keterjangkauan jaringan ke hub/cabang.
- Aturan bisnis: masukan host divalidasi secara ketat.

**FR-G2 — Tugas Maintenance**
- Aktor: Staff.
- Operasi: `RunMaintenance(task)`.
- Fungsi: menjalankan rutinitas pemeliharaan yang disetujui.
- Aturan bisnis: hanya staff yang berhak; otorisasi diverifikasi di sisi server.

**FR-G3 — Status Sistem**
- Aktor: Staff.
- Operasi: `SystemInfo()`.
- Output: informasi kesehatan/versi layanan.
- Aturan bisnis: hanya menampilkan informasi non-sensitif.

### 4.8 Modul H — Administrasi

**FR-H1 — Reset Data (Operator)**
- Aktor: Operator.
- Operasi: `ResetDatabase(password)`.
- Fungsi: mengembalikan data ke kondisi awal (seed). Dilindungi kata sandi operator.

---

## 5. Spesifikasi Antarmuka (API)

- Protokol: **gRPC**, dengan **gRPC-Web** untuk konsumsi dari browser.
- Service: **`nusakirim.ShipmentService`**.
- Kontrak lengkap (message & field) tersedia pada berkas **`shipping.proto`** (lampiran terpisah).

Ringkasan operasi:

| Operasi (RPC) | Aktor | Tujuan |
|---|---|---|
| `Login` | Anonim | Autentikasi & penerbitan token |
| `UpdateAccount` | Pelanggan | Perbarui data akun sendiri |
| `TrackShipment` | Anonim | Lacak resi publik |
| `SearchShipments` | Staff | Cari kiriman berdasarkan penerima |
| `GetShipment` | Pelanggan/Staff | Detail kiriman |
| `CancelShipment` | Pemilik/Staff | Batalkan kiriman |
| `DownloadDocument` | Terautentikasi | Unduh dokumen kiriman |
| `FetchExternalTracking` | Staff | Ambil status dari mitra kurir |
| `ImportShipmentBatch` | Staff | Impor batch kiriman |
| `SubmitFeedback` / `ListFeedback` | Pengguna | Ulasan pengiriman |
| `CheckHubConnectivity` | Staff | Diagnostik jaringan hub |
| `RunMaintenance` | Staff | Rutinitas pemeliharaan |
| `SystemInfo` | Staff | Informasi kesehatan layanan |
| `ResetDatabase` | Operator | Kembalikan data ke seed |

---

## 6. Model Data

**Customer** — `id, username, password, email, role, full_name, phone, address`
**Shipment** — `id, tracking_no, sender_name, recipient_name, recipient_address, recipient_phone, weight_kg, status, cost, notes, owner_id`
**Feedback** — `id, name, rating (1–5), comment`

Data yang tergolong sensitif: kredensial pelanggan, serta data kontak penerima
(`recipient_phone`, `recipient_address`).

---

## 7. Kebutuhan Non-Fungsional

### 7.1 Keamanan
- **NFR-SEC-1:** Fitur yang memerlukan identitas hanya dapat diakses setelah autentikasi.
- **NFR-SEC-2:** Otorisasi berbasis peran — pelanggan hanya mengakses data miliknya; fitur operasional hanya untuk staff. Keputusan otorisasi diverifikasi di sisi server.
- **NFR-SEC-3:** Seluruh masukan pengguna divalidasi/di-sanitasi sebelum digunakan pada query basis data, akses berkas, pemanggilan URL, perintah sistem, atau deserialisasi.
- **NFR-SEC-4:** Kredensial disimpan menggunakan mekanisme hashing kata sandi yang kuat.
- **NFR-SEC-5:** Token sesi terlindungi integritasnya; token tidak valid ditolak.
- **NFR-SEC-6:** Percobaan login yang gagal berulang dibatasi (rate limiting / lockout).
- **NFR-SEC-7:** Data sensitif dan konfigurasi internal tidak diekspos ke pihak tidak berhak.
- **NFR-SEC-8:** Komunikasi mendukung TLS.

### 7.2 Kinerja
- **NFR-PERF-1:** Operasi baca umum (lacak, detail) < 500 ms pada beban normal.

### 7.3 Ketersediaan
- **NFR-AVA-1:** Layanan berjalan sebagai kontainer dengan kebijakan auto-restart.

### 7.4 Kompatibilitas
- **NFR-CMP-1:** Portal berjalan pada peramban modern (Chromium, Firefox, Safari terbaru).

### 7.5 Usability
- **NFR-USA-1:** Antarmuka berbahasa Indonesia, responsif untuk desktop & mobile.

---

## 8. Lingkungan & Akses

| Lingkungan | Alamat | Keterangan |
|---|---|---|
| Portal Web | `https://pocpoc.my.id:8181` | SPA |
| API gRPC (TLS) | `grpcs://pocpoc.my.id:50443` | gRPC over TLS |
| API gRPC | `pocpoc.my.id:50051` | gRPC (plaintext) |

Akses dibatasi oleh IP allowlist (hubungi operator untuk whitelist). Kredensial akun
diberikan terpisah kepada pihak terkait.

---

## Lampiran A — Peran & Data Awal (Seed)

Akun awal yang tersedia di lingkungan (kata sandi diberikan terpisah):

| Username | Peran | Keterangan |
|---|---|---|
| `ops` | staff | Akun operasional |
| `budi` | customer | Memiliki kiriman NK1001, NK1004 |
| `sari` | customer | Memiliki kiriman NK1002 |
| `andi` | customer | Memiliki kiriman NK1003 |

Contoh nomor resi: `NK1001`–`NK1004`.

---

*Akhir dokumen. Kontrak API terperinci: lihat `shipping.proto`.*
