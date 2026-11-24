"""Logika bisnis WarungKu. Tidak bergantung pada Flask supaya mudah diuji."""
from dataclasses import dataclass
from datetime import date, timedelta
from database import db_session
from psycopg.errors import UniqueViolation, CheckViolation, ForeignKeyViolation


class InventoryError(ValueError):
    """Kesalahan input atau aturan stok."""


def positive_int(value, name, allow_zero=False):
    try:
        if isinstance(value, bool) or str(value).strip() == '':
            raise ValueError
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise InventoryError(f'{name} harus berupa bilangan bulat.')
    if number < 0 or (number == 0 and not allow_zero):
        raise InventoryError(f'{name} harus {"minimal 0" if allow_zero else "lebih dari 0"}.')
    return number


@dataclass
class Produk:
    sku: str
    nama: str
    harga_modal: int
    harga_jual: int
    stok: int = 0

    def nilai_persediaan(self):
        return self.harga_modal * self.stok


class ProdukMakanan(Produk):
    def __init__(self, sku, nama, harga_modal, harga_jual, stok=0, expired=None):
        super().__init__(sku, nama, harga_modal, harga_jual, stok)
        self.expired = expired

    def keterangan(self):
        return f'{self.nama} | Kedaluwarsa: {self.expired or "tidak diisi"}'


class ProdukNonMakanan(Produk):
    def keterangan(self):
        return f'{self.nama} | Non-makanan'


class SupplierService:
    def list(self):
        with db_session() as db:
            return db.execute('SELECT * FROM suppliers WHERE active=TRUE ORDER BY name').fetchall()

    def save(self, name, phone='', address='', supplier_id=None):
        name = str(name).strip()
        if not name:
            raise InventoryError('Nama supplier harus diisi.')
        if len(name) > 120 or len(str(phone)) > 40 or len(str(address)) > 250:
            raise InventoryError('Data supplier terlalu panjang.')
        with db_session() as db:
            try:
                if supplier_id is None:
                    db.execute('INSERT INTO suppliers(name,phone,address) VALUES(%s,%s,%s)', (name, phone.strip(), address.strip()))
                else:
                    cur = db.execute('UPDATE suppliers SET name=%s,phone=%s,address=%s WHERE id=%s AND active=TRUE',
                               (name, phone.strip(), address.strip(), supplier_id))
                    if cur.rowcount == 0:
                        raise InventoryError('Supplier tidak ditemukan.')
            except (UniqueViolation, CheckViolation, ForeignKeyViolation):
                raise InventoryError('Nama supplier sudah digunakan.')

    def archive(self, supplier_id):
        with db_session() as db:
            db.execute('UPDATE suppliers SET active=FALSE WHERE id=%s', (supplier_id,))


class InventarisService:
    def products(self, search='', category='', include_inactive=False):
        sql = '''SELECT p.*, s.name AS supplier_name FROM products p
                 LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1'''
        params = []
        if not include_inactive:
            sql += ' AND p.active=TRUE'
        if search:
            sql += ' AND (p.name ILIKE %s OR p.sku ILIKE %s)'
            params.extend([f'%{search}%', f'%{search}%'])
        if category:
            sql += ' AND p.category=%s'
            params.append(category)
        sql += ' ORDER BY p.name'
        with db_session() as db:
            return db.execute(sql, params).fetchall()

    def get_product(self, product_id, active_only=True):
        with db_session() as db:
            query = 'SELECT * FROM products WHERE id=%s' + (' AND active=TRUE' if active_only else '')
            row = db.execute(query, (product_id,)).fetchone()
            if row is None:
                raise InventoryError('Produk tidak ditemukan.')
            return row

    def save_product(self, data, product_id=None):
        sku = str(data.get('sku', '')).strip().upper()
        name = str(data.get('name', '')).strip()
        if not sku or not name:
            raise InventoryError('Kode dan nama produk wajib diisi.')
        if len(sku) > 64 or len(name) > 150:
            raise InventoryError('Kode atau nama produk terlalu panjang.')
        cost = positive_int(data.get('cost'), 'Harga modal', allow_zero=True)
        price = positive_int(data.get('price'), 'Harga jual', allow_zero=True)
        min_stock = positive_int(data.get('min_stock', 5), 'Batas stok', allow_zero=True)
        category = str(data.get('category', '')).strip() or 'Lainnya'
        if len(category) > 80:
            raise InventoryError('Kategori terlalu panjang.')
        expiry = str(data.get('expiry_date', '')).strip() or None
        if expiry:
            try:
                date.fromisoformat(expiry)
            except ValueError:
                raise InventoryError('Format tanggal kedaluwarsa tidak valid.')
        supplier_id = data.get('supplier_id') or None
        if supplier_id:
            supplier_id = positive_int(supplier_id, 'ID supplier')
        with db_session() as db:
            if supplier_id and not db.execute('SELECT 1 FROM suppliers WHERE id=%s AND active=TRUE', (supplier_id,)).fetchone():
                raise InventoryError('Supplier tidak ditemukan.')
            try:
                if product_id is None:
                    db.execute('''INSERT INTO products(sku,name,category,cost,price,min_stock,expiry_date,supplier_id)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''', (sku,name,category,cost,price,min_stock,expiry,supplier_id))
                else:
                    cur = db.execute('''UPDATE products SET sku=%s,name=%s,category=%s,cost=%s,price=%s,min_stock=%s,
                        expiry_date=%s,supplier_id=%s WHERE id=%s AND active=TRUE''',
                        (sku,name,category,cost,price,min_stock,expiry,supplier_id,product_id))
                    if cur.rowcount == 0:
                        raise InventoryError('Produk tidak ditemukan.')
            except (UniqueViolation, CheckViolation, ForeignKeyViolation):
                raise InventoryError('Kode produk sudah digunakan atau data tidak valid.')

    def archive_product(self, product_id):
        with db_session() as db:
            cur = db.execute('UPDATE products SET active=FALSE WHERE id=%s AND active=TRUE', (product_id,))
            if cur.rowcount == 0:
                raise InventoryError('Produk tidak ditemukan.')

    def move_stock(self, product_id, kind, amount, reason):
        """Update stok & riwayat secara atomik dalam satu transaksi."""
        if kind not in ('IN', 'OUT', 'ADJUST'):
            raise InventoryError('Jenis mutasi tidak dikenal.')
        amount = positive_int(amount, 'Jumlah') if kind != 'ADJUST' else positive_int(amount, 'Stok hasil penyesuaian', allow_zero=True)
        reason = str(reason).strip()
        if not reason:
            raise InventoryError('Alasan mutasi wajib diisi.')
        if len(reason) > 500:
            raise InventoryError('Alasan mutasi terlalu panjang.')
        with db_session() as db:
            product = db.execute('SELECT stock FROM products WHERE id=%s AND active=TRUE FOR UPDATE', (product_id,)).fetchone()
            if product is None:
                raise InventoryError('Produk tidak ditemukan.')
            current = product['stock']
            next_stock = (current + amount if kind == 'IN' else current - amount if kind == 'OUT' else amount)
            if next_stock < 0:
                raise InventoryError(f'Stok tidak cukup. Stok tersedia: {current}.')
            change = next_stock - current
            if change == 0:
                raise InventoryError('Stok tidak berubah.')
            db.execute('UPDATE products SET stock=%s WHERE id=%s', (next_stock, product_id))
            db.execute('''INSERT INTO movements(product_id,type,qty_change,stock_after,reason)
                VALUES(%s,%s,%s,%s,%s)''', (product_id, kind, change, next_stock, reason))
            return next_stock

    def movements(self, limit=200):
        with db_session() as db:
            return db.execute('''SELECT m.*,p.name,p.sku FROM movements m
                  JOIN products p ON m.product_id=p.id ORDER BY m.id DESC LIMIT %s''', (limit,)).fetchall()


class LaporanService:
    def summary(self):
        with db_session() as db:
            sums = db.execute('''SELECT COUNT(*) AS product_count, COALESCE(SUM(stock),0) AS units,
                  COALESCE(SUM(stock*cost),0) AS inventory_value,
                  COALESCE(SUM(CASE WHEN stock<=min_stock THEN 1 ELSE 0 END),0) AS low_count
                  FROM products WHERE active=TRUE''').fetchone()
            low = db.execute('''SELECT * FROM products WHERE active=TRUE AND stock<=min_stock
                  ORDER BY stock ASC,name LIMIT 12''').fetchall()
            upcoming = (date.today() + timedelta(days=30)).isoformat()
            expiring = db.execute('''SELECT * FROM products WHERE active=TRUE AND expiry_date IS NOT NULL
                  AND expiry_date<=%s ORDER BY expiry_date LIMIT 12''', (upcoming,)).fetchall()
            recent = db.execute('''SELECT m.*,p.name FROM movements m JOIN products p ON p.id=m.product_id
                   ORDER BY m.id DESC LIMIT 8''').fetchall()
            return {'summary': sums, 'low': low, 'expiring': expiring, 'recent': recent}

    def movement_totals(self):
        with db_session() as db:
            return db.execute('''SELECT date(created_at) AS day,
                COALESCE(SUM(CASE WHEN qty_change>0 THEN qty_change ELSE 0 END),0) AS masuk,
                COALESCE(SUM(CASE WHEN qty_change<0 THEN -qty_change ELSE 0 END),0) AS keluar
                FROM movements GROUP BY date(created_at) ORDER BY day DESC LIMIT 30''').fetchall()

    def most_outgoing(self):
        with db_session() as db:
            return db.execute('''SELECT p.name, p.sku, SUM(-m.qty_change) AS jumlah
                FROM movements m JOIN products p ON p.id=m.product_id
                WHERE m.qty_change<0 AND m.type='OUT'
                GROUP BY p.id ORDER BY jumlah DESC LIMIT 10''').fetchall()
