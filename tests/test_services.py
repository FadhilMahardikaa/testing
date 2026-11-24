import os
import unittest

# Wajib database tes terpisah. Jangan gunakan DATABASE_URL produksi.
TEST_URL = os.environ.get('WARUNGKU_TEST_DATABASE_URL')
if TEST_URL:
    os.environ['DATABASE_URL'] = TEST_URL
from database import init_db
from services import (InventarisService, InventoryError, LaporanService,
                      SupplierService, ProdukMakanan, ProdukNonMakanan)


@unittest.skipUnless(TEST_URL, "Atur WARUNGKU_TEST_DATABASE_URL ke PostgreSQL khusus tes")
class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.inv = InventarisService()
        self.sup = SupplierService()
        self.reports = LaporanService()
        import uuid
        self.sku = 'T' + uuid.uuid4().hex[:9].upper()
        self.inv.save_product({'sku':self.sku, 'name':'Barang Test', 'cost':'2500',
                               'price':'3500', 'min_stock':'3', 'category':'Makanan'})
        self.p = next(x for x in self.inv.products() if x['sku'] == self.sku)

    def test_masuk_keluar_dan_nilai(self):
        self.assertEqual(self.inv.move_stock(self.p['id'], 'IN', '10', 'Terima supplier'), 10)
        self.assertEqual(self.inv.move_stock(self.p['id'], 'OUT', '4', 'Barang rusak'), 6)
        self.assertEqual(self.inv.get_product(self.p['id'])['stock'], 6)
        self.assertGreaterEqual(self.reports.summary()['summary']['inventory_value'], 15000)

    def test_stok_tidak_boleh_negatif(self):
        with self.assertRaises(InventoryError):
            self.inv.move_stock(self.p['id'], 'OUT', 4, 'Rusak')
        self.assertEqual(self.inv.get_product(self.p['id'])['stock'], 0)

    def test_koreksi_opname(self):
        self.inv.move_stock(self.p['id'], 'IN', 8, 'Restock')
        self.assertEqual(self.inv.move_stock(self.p['id'], 'ADJUST', 3, 'Opname fisik'), 3)
        movement = next(x for x in self.inv.movements() if x['product_id'] == self.p['id'])
        self.assertEqual(movement['qty_change'], -5)

    def test_input_invalid(self):
        for n in ('-1', '2.5', 'abc', '0'):
            with self.assertRaises(InventoryError):
                self.inv.move_stock(self.p['id'], 'IN', n, 'Restock')

    def test_arsip_produk(self):
        self.inv.archive_product(self.p['id'])
        self.assertFalse(any(x['id'] == self.p['id'] for x in self.inv.products()))
        with self.assertRaises(InventoryError):
            self.inv.move_stock(self.p['id'], 'IN', 1, 'Tes')

    def test_inheritance_polymorphism(self):
        items = [ProdukMakanan('A','Roti',100,150,1,'2026-12-31'),
                 ProdukNonMakanan('B','Sabun',100,150,2)]
        self.assertIn('Kedaluwarsa', items[0].keterangan())
        self.assertIn('Non-makanan', items[1].keterangan())
        self.assertEqual(items[1].nilai_persediaan(), 200)


if __name__ == '__main__':
    unittest.main()
