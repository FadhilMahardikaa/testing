"""Koneksi SQLite (tanpa perlu database eksternal / PostgreSQL).
Bekerja secara lokal dan di Vercel (/tmp/warungku.db).
Data otomatis terisi contoh produk & supplier jika kosong.
"""
import os
import sqlite3
from contextlib import contextmanager

# Di serverless Vercel, direktori /tmp adalah satu-satunya lokasi yang bisa ditulis.
if os.path.isdir('/tmp'):
    DB_FILE = '/tmp/warungku.db'
else:
    DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'warungku.db')


def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def connect():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Idempotent: membuat skema tabel dan data awal jika masih kosong."""
    with db_session() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1
        )''')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_name_ci ON suppliers(name COLLATE NOCASE)')

        db.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Lainnya',
            cost INTEGER NOT NULL CHECK(cost >= 0),
            price INTEGER NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            min_stock INTEGER NOT NULL DEFAULT 5 CHECK(min_stock >= 0),
            expiry_date TEXT,
            supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku_ci ON products(sku COLLATE NOCASE)')

        db.execute('''CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            type TEXT NOT NULL CHECK(type IN ('IN','OUT','ADJUST')),
            qty_change INTEGER NOT NULL CHECK(qty_change != 0),
            stock_after INTEGER NOT NULL CHECK(stock_after >= 0),
            reason TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_movements_product ON movements(product_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_movements_created ON movements(created_at)')

        # Seed data awal jika belum ada data
        cur = db.execute('SELECT COUNT(*) AS count FROM products')
        if cur.fetchone()['count'] == 0:
            db.execute('''INSERT INTO suppliers (name, phone, address) VALUES
                ('PT Sumber Makmur', '081234567890', 'Jl. Merdeka No. 10, Jakarta'),
                ('Wings Group Distributor', '081398765432', 'Kawasan Industri Cikarang'),
                ('CV Berkah Sembako', '081122334455', 'Pasar Induk Kramat Jati')
            ''')
            
            db.execute('''INSERT INTO products (sku, name, category, cost, price, stock, min_stock, expiry_date, supplier_id) VALUES
                ('IND001', 'Indomie Goreng Original', 'Makanan', 2800, 3500, 48, 10, '2027-06-30', 1),
                ('MNK001', 'Minyak Goreng Bimoli 1L', 'Sembako', 15000, 18000, 14, 5, '2027-12-31', 3),
                ('BRS001', 'Beras Ramos Super 5kg', 'Sembako', 64000, 72000, 8, 5, NULL, 3),
                ('SBN001', 'Sabun Mandi Lifebuoy Red', 'Kebersihan', 3500, 4500, 3, 5, '2028-01-01', 2),
                ('SUS001', 'Susu UHT Ultramilk 250ml', 'Minuman', 5000, 6500, 20, 5, '2026-12-05', 1)
            ''')

            db.execute('''INSERT INTO movements (product_id, type, qty_change, stock_after, reason) VALUES
                (1, 'IN', 48, 48, 'Stok awal gudang'),
                (2, 'IN', 14, 14, 'Stok awal gudang'),
                (3, 'IN', 8, 8, 'Stok awal gudang'),
                (4, 'IN', 3, 3, 'Stok awal gudang (menipis)'),
                (5, 'IN', 20, 20, 'Stok awal gudang')
            ''')
