"""SQLite bootstrap + seed data for the NusaKirim shipping portal.

Passwords are stored as unsalted MD5 (a planted cryptographic weakness).
"""
import hashlib
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "nusakirim.db")


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force: bool = False) -> None:
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = connect()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT UNIQUE,
            password  TEXT,             -- md5, unsalted
            email     TEXT,
            role      TEXT,             -- 'customer' | 'staff'
            full_name TEXT,
            phone     TEXT,
            address   TEXT
        );
        CREATE TABLE IF NOT EXISTS shipments (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_no       TEXT UNIQUE,
            sender_name       TEXT,
            recipient_name    TEXT,
            recipient_address TEXT,
            recipient_phone   TEXT,
            weight_kg         REAL,
            status            TEXT,
            cost              INTEGER,
            notes             TEXT,
            owner_id          INTEGER      -- customer who booked it
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT,
            rating  INTEGER,
            comment TEXT
        );
        """
    )

    cur.execute("SELECT COUNT(*) AS n FROM customers")
    if cur.fetchone()["n"] == 0:
        customers = [
            ("ops",   md5("Ops#2024"), "ops@nusakirim.id",   "staff",    "Operasional Pusat", "+62811000001", "Kantor Pusat, Jakarta"),
            ("budi",  md5("budi123"),  "budi@mail.com",      "customer", "Budi Santoso",      "+62812345678", "Jl. Merdeka 10, Bandung"),
            ("sari",  md5("sari123"),  "sari@mail.com",      "customer", "Sari Dewi",         "+62813555777", "Jl. Melati 5, Surabaya"),
            ("andi",  md5("andi123"),  "andi@mail.com",      "customer", "Andi Wijaya",       "+62814222999", "Jl. Kenanga 21, Medan"),
        ]
        cur.executemany(
            "INSERT INTO customers (username,password,email,role,full_name,phone,address) "
            "VALUES (?,?,?,?,?,?,?)",
            customers,
        )
        shipments = [
            ("NK1001", "Toko Elektronik Jaya", "Budi Santoso", "Jl. Merdeka 10, Bandung",  "+62812345678", 2.5, "In Transit", 45000,  "Fragile - handle with care", 2),
            ("NK1002", "Distro Melati",        "Sari Dewi",    "Jl. Melati 5, Surabaya",   "+62813555777", 1.2, "Delivered",  22000,  "Leave at front desk",        3),
            ("NK1003", "Herbal Sehat",         "Andi Wijaya",  "Jl. Kenanga 21, Medan",    "+62814222999", 0.8, "Out for Delivery", 30000, "COD Rp150.000",           4),
            ("NK1004", "Toko Buku Cerdas",     "Budi Santoso", "Jl. Merdeka 10, Bandung",  "+62812345678", 3.1, "Processing", 51000,  "Signature required",         2),
        ]
        cur.executemany(
            "INSERT INTO shipments (tracking_no,sender_name,recipient_name,recipient_address,"
            "recipient_phone,weight_kg,status,cost,notes,owner_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            shipments,
        )
        cur.execute(
            "INSERT INTO feedback (name, rating, comment) VALUES (?, ?, ?)",
            ("Budi S.", 5, "Paket sampai cepat, kurir ramah. Terima kasih NusaKirim!"),
        )
        conn.commit()

    conn.close()


if __name__ == "__main__":
    init_db(force=True)
    print(f"[+] database initialized at {DB_PATH}")
