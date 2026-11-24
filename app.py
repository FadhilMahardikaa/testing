"""WarungKu: Flask routes. Jalankan: python app.py"""
import csv
import hmac
import threading
import io
import os
import secrets
from functools import wraps
from flask import Flask, Response, flash, redirect, render_template, request, send_from_directory, session, url_for, abort
from werkzeug.security import check_password_hash
from database import init_db
from services import InventarisService, InventoryError, SupplierService, LaporanService

# Di Vercel, file statis dilayani CDN dari folder public/, bukan static_folder Flask.
app = Flask(__name__, static_folder=None)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_HOSTED = os.getenv('VERCEL') == '1' or os.getenv('WARUNGKU_PRODUCTION') == '1'
SECRET = os.getenv('WARUNGKU_SECRET_KEY')
PASSWORD_HASH = os.getenv('WARUNGKU_ADMIN_PASSWORD_HASH')

if IS_HOSTED and (not SECRET or not PASSWORD_HASH or not os.getenv('DATABASE_URL')):
    raise RuntimeError('Atur DATABASE_URL, WARUNGKU_SECRET_KEY, WARUNGKU_ADMIN_PASSWORD_HASH di Vercel.')
# Untuk pengujian lokal juga butuh PostgreSQL, tidak menggunakan password demo.
if not SECRET or not PASSWORD_HASH:
    raise RuntimeError('Atur WARUNGKU_SECRET_KEY dan WARUNGKU_ADMIN_PASSWORD_HASH sebelum menjalankan aplikasi.')

app.secret_key = SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=IS_HOSTED,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 2,
    MAX_CONTENT_LENGTH=1_048_576,
)
inventory = InventarisService()
suppliers = SupplierService()
reports = LaporanService()
_initialized = False
_init_lock = threading.Lock()


@app.before_request
def initialize_and_headers():
    global _initialized
    if not _initialized:
        with _init_lock:
            if not _initialized:
                init_db()
                _initialized = True


@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    if IS_HOSTED:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def protected(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(24)
    return session['csrf']


@app.before_request
def check_csrf():
    if request.method == 'POST' and not hmac.compare_digest(str(session.get('csrf', '')), str(request.form.get('_csrf', '_'))):
        abort(400, description='Token keamanan tidak valid. Muat ulang halaman dan coba lagi.')


app.jinja_env.globals['csrf_token'] = csrf_token
app.jinja_env.filters['rupiah'] = lambda n: 'Rp' + f'{int(n or 0):,}'.replace(',', '.')


@app.get('/style.css')
def style_css():
    """Dipakai saat jalan lokal. Di Vercel, public/style.css dilayani CDN lebih dulu."""
    return send_from_directory(os.path.join(BASE_DIR, 'public'), 'style.css', mimetype='text/css')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if check_password_hash(PASSWORD_HASH, request.form.get('password', '')):
            session.clear()
            session['logged_in'] = True
            session.permanent = True
            flash('Berhasil masuk.', 'success')
            return redirect(url_for('dashboard'))
        flash('Kata sandi salah.', 'error')
    return render_template('login.html')


@app.post('/logout')
@protected
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.get('/')
@protected
def dashboard():
    return render_template('dashboard.html', data=reports.summary(), active='dashboard')


@app.get('/produk')
@protected
def products():
    q = request.args.get('q', '').strip()
    return render_template('products.html', products=inventory.products(q), search=q, active='products')


@app.route('/produk/tambah', methods=['GET', 'POST'])
@protected
def product_add():
    if request.method == 'POST':
        try:
            inventory.save_product(request.form)
            flash('Produk berhasil ditambahkan. Masukkan stok awal melalui Barang Masuk.', 'success')
            return redirect(url_for('products'))
        except InventoryError as exc:
            flash(str(exc), 'error')
    return render_template('product_form.html', item=None, supplier_list=suppliers.list(), active='products')


@app.route('/produk/<int:product_id>/edit', methods=['GET', 'POST'])
@protected
def product_edit(product_id):
    try:
        item = inventory.get_product(product_id)
    except InventoryError:
        abort(404)
    if request.method == 'POST':
        try:
            inventory.save_product(request.form, product_id)
            flash('Produk berhasil diperbarui.', 'success')
            return redirect(url_for('products'))
        except InventoryError as exc:
            flash(str(exc), 'error')
    return render_template('product_form.html', item=item, supplier_list=suppliers.list(), active='products')


@app.post('/produk/<int:product_id>/arsip')
@protected
def product_archive(product_id):
    try:
        inventory.archive_product(product_id)
        flash('Produk berhasil diarsipkan.', 'success')
    except InventoryError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('products'))


@app.route('/mutasi', methods=['GET', 'POST'])
@protected
def movements():
    if request.method == 'POST':
        try:
            inventory.move_stock(int(request.form.get('product_id', '0')),
                                 request.form.get('kind', ''), request.form.get('amount', ''),
                                 request.form.get('reason', ''))
            flash('Pergerakan stok berhasil dicatat.', 'success')
            return redirect(url_for('movements'))
        except (InventoryError, ValueError) as exc:
            flash(str(exc) if isinstance(exc, InventoryError) else 'Pilih produk yang valid.', 'error')
    return render_template('movements.html', products=inventory.products(), rows=inventory.movements(),
                           selected_product=request.args.get('produk', type=int), active='movements')


@app.route('/supplier', methods=['GET', 'POST'])
@protected
def supplier_list():
    if request.method == 'POST':
        try:
            suppliers.save(request.form.get('name', ''), request.form.get('phone', ''), request.form.get('address', ''))
            flash('Supplier berhasil ditambahkan.', 'success')
            return redirect(url_for('supplier_list'))
        except InventoryError as exc:
            flash(str(exc), 'error')
    return render_template('suppliers.html', rows=suppliers.list(), active='suppliers')


@app.post('/supplier/<int:supplier_id>/edit')
@protected
def supplier_edit(supplier_id):
    try:
        suppliers.save(request.form.get('name', ''), request.form.get('phone', ''),
                       request.form.get('address', ''), supplier_id=supplier_id)
        flash('Supplier berhasil diperbarui.', 'success')
    except InventoryError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('supplier_list'))


@app.post('/supplier/<int:supplier_id>/arsip')
@protected
def supplier_archive(supplier_id):
    suppliers.archive(supplier_id)
    flash('Supplier berhasil diarsipkan.', 'success')
    return redirect(url_for('supplier_list'))


@app.get('/laporan')
@protected
def report_page():
    return render_template('reports.html', data=reports.summary(), days=reports.movement_totals(),
                           outgoing=reports.most_outgoing(), active='reports')


@app.get('/laporan/export.csv')
@protected
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Kode', 'Nama', 'Kategori', 'Harga Modal', 'Harga Jual', 'Stok', 'Stok Minimum', 'Nilai Persediaan', 'Kedaluwarsa', 'Supplier'])
    for p in inventory.products():
        writer.writerow([p['sku'], p['name'], p['category'], p['cost'], p['price'], p['stock'],
                         p['min_stock'], p['stock'] * p['cost'], p['expiry_date'] or '', p['supplier_name'] or ''])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': 'attachment; filename=laporan_inventaris_warungku.csv',
        'Cache-Control': 'no-store'})


@app.get('/laporan/mutasi.csv')
@protected
def export_movements_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Waktu UTC', 'Kode Barang', 'Nama Barang', 'Jenis Mutasi',
                     'Perubahan Unit', 'Stok Sesudah', 'Keterangan'])
    for m in inventory.movements(limit=10000):
        writer.writerow([m['created_at'].isoformat(), m['sku'], m['name'], m['type'],
                         m['qty_change'], m['stock_after'], m['reason']])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=riwayat_mutasi_warungku.csv',
                             'Cache-Control': 'no-store'})


if __name__ == '__main__':
    app.run(debug=False)
