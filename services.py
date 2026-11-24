"""Logika bisnis WarungKu. Murni in-memory tanpa ketergantungan database eksternal."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from database import DATA, init_db


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
        return [dict(s) for s in DATA['suppliers'] if s.get('active', True)]

    def save(self, name, phone='', address='', supplier_id=None):
        name = str(name).strip()
        if not name:
            raise InventoryError('Nama supplier harus diisi.')
        if len(name) > 120 or len(str(phone)) > 40 or len(str(address)) > 250:
            raise InventoryError('Data supplier terlalu panjang.')

        # Cek duplikat nama
        for s in DATA['suppliers']:
            if s.get('active', True) and s['name'].lower() == name.lower():
                if supplier_id is None or s['id'] != supplier_id:
                    raise InventoryError('Nama supplier sudah digunakan.')

        if supplier_id is None:
            new_id = DATA['next_supplier_id']
            DATA['next_supplier_id'] += 1
            DATA['suppliers'].append({
                'id': new_id,
                'name': name,
                'phone': phone.strip(),
                'address': address.strip(),
                'active': True
            })
        else:
            for s in DATA['suppliers']:
                if s['id'] == supplier_id and s.get('active', True):
                    s['name'] = name
                    s['phone'] = phone.strip()
                    s['address'] = address.strip()
                    return
            raise InventoryError('Supplier tidak ditemukan.')

    def archive(self, supplier_id):
        for s in DATA['suppliers']:
            if s['id'] == supplier_id:
                s['active'] = False
                return


class InventarisService:
    def products(self, search='', category='', include_inactive=False):
        suppliers_map = {s['id']: s['name'] for s in DATA['suppliers']}
        result = []
        q = search.lower().strip()
        for p in DATA['products']:
            if not include_inactive and not p.get('active', True):
                continue
            if q and q not in p['name'].lower() and q not in p['sku'].lower():
                continue
            if category and p.get('category') != category:
                continue
            item = dict(p)
            item['supplier_name'] = suppliers_map.get(p.get('supplier_id'), '')
            result.append(item)
        result.sort(key=lambda x: x['name'])
        return result

    def get_product(self, product_id, active_only=True):
        for p in DATA['products']:
            if p['id'] == product_id:
                if active_only and not p.get('active', True):
                    continue
                return dict(p)
        raise InventoryError('Produk tidak ditemukan.')

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

        # Cek duplikat SKU
        for p in DATA['products']:
            if p.get('active', True) and p['sku'].upper() == sku:
                if product_id is None or p['id'] != product_id:
                    raise InventoryError('Kode produk sudah digunakan atau data tidak valid.')

        if product_id is None:
            new_id = DATA['next_product_id']
            DATA['next_product_id'] += 1
            DATA['products'].append({
                'id': new_id,
                'sku': sku,
                'name': name,
                'category': category,
                'cost': cost,
                'price': price,
                'stock': 0,
                'min_stock': min_stock,
                'expiry_date': expiry or '',
                'supplier_id': supplier_id,
                'active': True,
                'created_at': datetime.now()
            })
        else:
            for p in DATA['products']:
                if p['id'] == product_id and p.get('active', True):
                    p['sku'] = sku
                    p['name'] = name
                    p['category'] = category
                    p['cost'] = cost
                    p['price'] = price
                    p['min_stock'] = min_stock
                    p['expiry_date'] = expiry or ''
                    p['supplier_id'] = supplier_id
                    return
            raise InventoryError('Produk tidak ditemukan.')

    def archive_product(self, product_id):
        for p in DATA['products']:
            if p['id'] == product_id and p.get('active', True):
                p['active'] = False
                return
        raise InventoryError('Produk tidak ditemukan.')

    def move_stock(self, product_id, kind, amount, reason):
        if kind not in ('IN', 'OUT', 'ADJUST'):
            raise InventoryError('Jenis mutasi tidak dikenal.')
        amount = positive_int(amount, 'Jumlah') if kind != 'ADJUST' else positive_int(amount, 'Stok hasil penyesuaian', allow_zero=True)
        reason = str(reason).strip()
        if not reason:
            raise InventoryError('Alasan mutasi wajib diisi.')
        if len(reason) > 500:
            raise InventoryError('Alasan mutasi terlalu panjang.')

        for p in DATA['products']:
            if p['id'] == product_id and p.get('active', True):
                current = p['stock']
                next_stock = (current + amount if kind == 'IN' else current - amount if kind == 'OUT' else amount)
                if next_stock < 0:
                    raise InventoryError(f'Stok tidak cukup. Stok tersedia: {current}.')
                change = next_stock - current
                if change == 0:
                    raise InventoryError('Stok tidak berubah.')
                p['stock'] = next_stock

                new_mov_id = DATA['next_movement_id']
                DATA['next_movement_id'] += 1
                DATA['movements'].append({
                    'id': new_mov_id,
                    'product_id': product_id,
                    'type': kind,
                    'qty_change': change,
                    'stock_after': next_stock,
                    'reason': reason,
                    'created_at': datetime.now()
                })
                return next_stock
        raise InventoryError('Produk tidak ditemukan.')

    def movements(self, limit=200):
        prod_map = {p['id']: p for p in DATA['products']}
        result = []
        for m in reversed(DATA['movements']):
            item = dict(m)
            p = prod_map.get(m['product_id'], {})
            item['name'] = p.get('name', 'Barang dihapus')
            item['sku'] = p.get('sku', '')
            result.append(item)
            if len(result) >= limit:
                break
        return result


class LaporanService:
    def summary(self):
        active_products = [p for p in DATA['products'] if p.get('active', True)]
        product_count = len(active_products)
        units = sum(p['stock'] for p in active_products)
        inventory_value = sum(p['stock'] * p['cost'] for p in active_products)
        low_count = sum(1 for p in active_products if p['stock'] <= p['min_stock'])

        low = [p for p in active_products if p['stock'] <= p['min_stock']]
        low.sort(key=lambda x: (x['stock'], x['name']))

        upcoming = (date.today() + timedelta(days=30)).isoformat()
        expiring = [p for p in active_products if p.get('expiry_date') and p['expiry_date'] <= upcoming]
        expiring.sort(key=lambda x: x['expiry_date'])

        prod_map = {p['id']: p for p in DATA['products']}
        recent = []
        for m in reversed(DATA['movements']):
            item = dict(m)
            p = prod_map.get(m['product_id'], {})
            item['name'] = p.get('name', 'Barang')
            recent.append(item)
            if len(recent) >= 8:
                break

        return {
            'summary': {
                'product_count': product_count,
                'units': units,
                'inventory_value': inventory_value,
                'low_count': low_count
            },
            'low': low[:12],
            'expiring': expiring[:12],
            'recent': recent
        }

    def movement_totals(self):
        daily = {}
        for m in DATA['movements']:
            dt = m['created_at']
            day = dt.strftime('%Y-%m-%d') if isinstance(dt, datetime) else str(dt)[:10]
            if day not in daily:
                daily[day] = {'day': day, 'masuk': 0, 'keluar': 0}
            if m['qty_change'] > 0:
                daily[day]['masuk'] += m['qty_change']
            elif m['qty_change'] < 0:
                daily[day]['keluar'] += (-m['qty_change'])
        sorted_days = sorted(daily.values(), key=lambda x: x['day'], reverse=True)
        return sorted_days[:30]

    def most_outgoing(self):
        prod_map = {p['id']: p for p in DATA['products']}
        out_counts = {}
        for m in DATA['movements']:
            if m['type'] == 'OUT' and m['qty_change'] < 0:
                pid = m['product_id']
                out_counts[pid] = out_counts.get(pid, 0) + (-m['qty_change'])
        result = []
        for pid, jumlah in out_counts.items():
            p = prod_map.get(pid)
            if p:
                result.append({'name': p['name'], 'sku': p['sku'], 'jumlah': jumlah})
        result.sort(key=lambda x: x['jumlah'], reverse=True)
        return result[:10]
