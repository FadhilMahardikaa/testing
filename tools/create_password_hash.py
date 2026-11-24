"""Jalankan: python tools/create_password_hash.py"""
import getpass
from werkzeug.security import generate_password_hash

password = getpass.getpass('Buat password admin (minimal 12 karakter): ')
confirmation = getpass.getpass('Ulangi password: ')
if password != confirmation or len(password) < 12:
    raise SystemExit('Password tidak sama atau kurang dari 12 karakter.')
print('\nSalin ini ke WARUNGKU_ADMIN_PASSWORD_HASH (bukan password asli):')
print(generate_password_hash(password, method='pbkdf2:sha256:600000'))
