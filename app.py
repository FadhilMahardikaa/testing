"""WarungKu: Flask routes. Siap jalan di Vercel tanpa password & tanpa database."""
import csv
import io
import os
import traceback
from flask import Flask, Response, flash, redirect, render_template, request, send_from_directory, session, url_for

# Tentukan direktori dasar secara dinamis (bekerja dari root atau folder api/)
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(current_dir, 'templates')):
    BASE_DIR = current_dir
else:
    BASE_DIR = os.path.abspath(os.path.join(current_dir, '..'))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'public'),
    static_url_path=''
)

app.secret_key = 'warungku-secret-key-tanpa-env-2026'

from database import init_db
from services import InventarisService, InventoryError, SupplierService, LaporanService

inventory = InventarisService()
suppliers = SupplierService()
reports = LaporanService()


@app.errorhandler(Exception)
def handle_any_error(e):
    trace = traceback.format_exc()
    return f"""
    <!doctype html>
    <html lang="id">
    <head><meta charset="utf-8"><title>Error</title></head>
    <body style="padding: 30px; font-family: sans-serif;">
      <h2 style="color: #e11d48;">Terjadi Kesalahan Sistem</h2>
      <pre style="background: #f1f5f9; padding: 15px; border-radius: 8px; overflow: auto;">{trace}</pre>
      <p><a href="/" style="color: #2563eb;">&larr; Kembali ke Dashboard</a></p>
    </body>
    </html>
    """, 500


@app.before_request
def ensure_initialized():
    init_db()
    session['logged_in'] = True  # Otomatis login, tanpa form password


app.jinja_env.globals['csrf_token'] = lambda: 'public_token'
app.jinja_env.filters['rupiah'] = lambda n: 'Rp' + f'{int(n or 0):,}'.replace(',', '.')


@app.get('/style.css')
def style_css():
    return send_from_directory(os.path.join(BASE_DIR, 'public'), 'style.css', mimetype='text/css')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Langsung arahkan ke dashboard tanpa password
    return redirect(url_for('dashboard'))


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    return redirect(url_for('dashboard'))


@app.get('/')
def dashboard():
    return render_template('dashboard.html', data=reports.summary(), active='dashboard')


@app.get('/produk')
def products():
    q = request.args.get('q', '').strip()
    return render_template('products.html', products=inventory.products(q), search=q, active='products')


@app.route('/produk/tambah', methods=['GET', 'POST'])
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
def product_edit(product_id):
    try:
        item = inventory.get_product(product_id)
    except InventoryError:
        return redirect(url_for('products'))
    if request.method == 'POST':
        try:
            inventory.save_product(request.form, product_id)
            flash('Produk berhasil diperbarui.', 'success')
            return redirect(url_for('products'))
        except InventoryError as exc:
            flash(str(exc), 'error')
    return render_template('product_form.html', item=item, supplier_list=suppliers.list(), active='products')


@app.post('/produk/<int:product_id>/arsip')
def product_archive(product_id):
    try:
        inventory.archive_product(product_id)
        flash('Produk berhasil diarsipkan.', 'success')
    except InventoryError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('products'))


@app.route('/mutasi', methods=['GET', 'POST'])
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
def supplier_edit(supplier_id):
    try:
        suppliers.save(request.form.get('name', ''), request.form.get('phone', ''),
                       request.form.get('address', ''), supplier_id=supplier_id)
        flash('Supplier berhasil diperbarui.', 'success')
    except InventoryError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('supplier_list'))


@app.post('/supplier/<int:supplier_id>/arsip')
def supplier_archive(supplier_id):
    suppliers.archive(supplier_id)
    flash('Supplier berhasil diarsipkan.', 'success')
    return redirect(url_for('supplier_list'))


@app.get('/laporan')
def report_page():
    return render_template('reports.html', data=reports.summary(), days=reports.movement_totals(),
                           outgoing=reports.most_outgoing(), active='reports')


@app.get('/laporan/export.csv')
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
def export_movements_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Waktu', 'Kode Barang', 'Nama Barang', 'Jenis Mutasi',
                     'Perubahan Unit', 'Stok Sesudah', 'Keterangan'])
    for m in inventory.movements(limit=10000):
        writer.writerow([m['created_at'], m['sku'], m['name'], m['type'],
                         m['qty_change'], m['stock_after'], m['reason']])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=riwayat_mutasi_warungku.csv',
                             'Cache-Control': 'no-store'})


if __name__ == '__main__':
    app.run(debug=True)
