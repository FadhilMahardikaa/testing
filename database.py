"""Penyimpanan data In-Memory murni untuk WarungKu.
Tidak membutuhkan database server, tidak membutuhkan file disk, 100% aman untuk serverless.
"""
from datetime import datetime

# State global in-memory
DATA = {
    'suppliers': [],
    'products': [],
    'movements': [],
    'next_supplier_id': 1,
    'next_product_id': 1,
    'next_movement_id': 1
}


def init_db():
    """Mengisi data awal jika kosong."""
    if not DATA['products']:
        DATA['suppliers'] = [
            {'id': 1, 'name': 'PT Sumber Makmur', 'phone': '081234567890', 'address': 'Jl. Merdeka No. 10, Jakarta', 'active': True},
            {'id': 2, 'name': 'Wings Group Distributor', 'phone': '081398765432', 'address': 'Kawasan Industri Cikarang', 'active': True},
            {'id': 3, 'name': 'CV Berkah Sembako', 'phone': '081122334455', 'address': 'Pasar Induk Kramat Jati', 'active': True},
        ]
        DATA['next_supplier_id'] = 4

        DATA['products'] = [
            {'id': 1, 'sku': 'IND001', 'name': 'Indomie Goreng Original', 'category': 'Makanan', 'cost': 2800, 'price': 3500, 'stock': 48, 'min_stock': 10, 'expiry_date': '2027-06-30', 'supplier_id': 1, 'active': True, 'created_at': datetime.now()},
            {'id': 2, 'sku': 'MNK001', 'name': 'Minyak Goreng Bimoli 1L', 'category': 'Sembako', 'cost': 15000, 'price': 18000, 'stock': 14, 'min_stock': 5, 'expiry_date': '2027-12-31', 'supplier_id': 3, 'active': True, 'created_at': datetime.now()},
            {'id': 3, 'sku': 'BRS001', 'name': 'Beras Ramos Super 5kg', 'category': 'Sembako', 'cost': 64000, 'price': 72000, 'stock': 8, 'min_stock': 5, 'expiry_date': '', 'supplier_id': 3, 'active': True, 'created_at': datetime.now()},
            {'id': 4, 'sku': 'SBN001', 'name': 'Sabun Mandi Lifebuoy Red', 'category': 'Kebersihan', 'cost': 3500, 'price': 4500, 'stock': 3, 'min_stock': 5, 'expiry_date': '2028-01-01', 'supplier_id': 2, 'active': True, 'created_at': datetime.now()},
            {'id': 5, 'sku': 'SUS001', 'name': 'Susu UHT Ultramilk 250ml', 'category': 'Minuman', 'cost': 5000, 'price': 6500, 'stock': 20, 'min_stock': 5, 'expiry_date': '2026-12-05', 'supplier_id': 1, 'active': True, 'created_at': datetime.now()},
        ]
        DATA['next_product_id'] = 6

        DATA['movements'] = [
            {'id': 1, 'product_id': 1, 'type': 'IN', 'qty_change': 48, 'stock_after': 48, 'reason': 'Stok awal gudang', 'created_at': datetime.now()},
            {'id': 2, 'product_id': 2, 'type': 'IN', 'qty_change': 14, 'stock_after': 14, 'reason': 'Stok awal gudang', 'created_at': datetime.now()},
            {'id': 3, 'product_id': 3, 'type': 'IN', 'qty_change': 8, 'stock_after': 8, 'reason': 'Stok awal gudang', 'created_at': datetime.now()},
            {'id': 4, 'product_id': 4, 'type': 'IN', 'qty_change': 3, 'stock_after': 3, 'reason': 'Stok awal gudang (menipis)', 'created_at': datetime.now()},
            {'id': 5, 'product_id': 5, 'type': 'IN', 'qty_change': 20, 'stock_after': 20, 'reason': 'Stok awal gudang', 'created_at': datetime.now()},
        ]
        DATA['next_movement_id'] = 6


# Inisialisasi saat modul dimuat
init_db()
