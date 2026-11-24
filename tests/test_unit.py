import unittest
from services import positive_int, InventoryError, ProdukMakanan, ProdukNonMakanan

class PurePythonTests(unittest.TestCase):
    def test_positive_integer(self):
        self.assertEqual(positive_int('8', 'stok'), 8)
        self.assertEqual(positive_int('0', 'stok', allow_zero=True), 0)

    def test_invalid_integer(self):
        for value in ('-3', '0', '2.5', 'abc', ''):
            with self.subTest(value=value):
                with self.assertRaises(InventoryError):
                    positive_int(value, 'stok')

    def test_inheritance_polymorphism(self):
        items = [ProdukMakanan('A', 'Roti', 2000, 3000, 5, '2026-12-01'),
                 ProdukNonMakanan('B', 'Sabun', 2500, 4000, 4)]
        self.assertIn('Kedaluwarsa', items[0].keterangan())
        self.assertIn('Non-makanan', items[1].keterangan())
        self.assertEqual(sum(p.nilai_persediaan() for p in items), 20000)

if __name__ == '__main__':
    unittest.main()
