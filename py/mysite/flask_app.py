import os
import base64
import math
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
import sqlite3
from datetime import datetime
from PIL import Image

app = Flask(__name__)

# Konfigurasi Path Absolut Folder Penyimpanan Foto (Aman untuk PythonAnywhere)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DATABASE = os.path.join(BASE_DIR, 'hama_padi_v3.db')
SECRET_DELETE_KEY = "c1nt4k4s1h" # Kode Rahasia Penghapusan

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Inisialisasi Database (Mendukung Hama 1-4)
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS log_hama (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            pred INTEGER,
            confidence REAL,
            lat INTEGER,
            arena INTEGER,
            ram INTEGER,
            foto_path TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ----------------- ENDPOINT API UNTUK ESP32-S3 -----------------
@app.route('/api/hama', methods=['POST'])
def receive_data():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Missing JSON payload"}), 400

        device_id = data.get('device_id', 'ESP32_NODE')
        pred = int(data.get('pred', 0))
        confidence = float(data.get('confidence', 0.0))
        lat = int(data.get('lat', 0))
        arena = int(data.get('arena', 0))
        ram = int(data.get('ram', 0))
        foto_b64 = data.get('foto', '')

        filename = "no_image.jpg"
        
        if foto_b64:
            foto_b64_clean = foto_b64.replace('\n', '').replace('\r', '').strip()
            raw_bytes = base64.b64decode(foto_b64_clean)
            
            if len(raw_bytes) == 9216:
                img = Image.frombytes('L', (96, 96), raw_bytes)
                filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                img.save(filepath, "JPEG")
            else:
                print(f"Peringatan: Ukuran biner tidak sesuai ({len(raw_bytes)} bytes)")
                img = Image.new('L', (96, 96), color=128) 
                filename = f"corrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                img.save(filepath, "JPEG")

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO log_hama (device_id, pred, confidence, lat, arena, ram, foto_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_id, pred, confidence, lat, arena, ram, filename))
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "message": f"Data saved as {filename}"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# API untuk Data Statistik (Chart.js)
@app.route('/api/hama/statistik', methods=['GET'])
def get_statistik():
    conn = get_db_connection()
    pie_data = [0, 0, 0, 0]
    for i in range(1, 5):
        row = conn.execute('SELECT COUNT(*) as total FROM log_hama WHERE pred = ?', (i,)).fetchone()
        pie_data[i-1] = row['total'] if row else 0

    line_labels = []
    line_values = []
    rows = conn.execute('''
        SELECT date(timestamp) as tgl, COUNT(*) as total 
        FROM log_hama 
        WHERE pred IN (1,2,3,4)
        GROUP BY tgl 
        ORDER BY tgl DESC 
        LIMIT 7
    ''').fetchall()
    
    for row in reversed(rows):
        line_labels.append(row['tgl'])
        line_values.append(row['total'])

    conn.close()
    return jsonify({
        "pie": pie_data,
        "line": {"labels": line_labels, "values": line_values}
    })

# ----------------- ENDPOINT PENGHAPUSAN SECURE (BACK-END VALIDATION) -----------------
@app.route('/clear', methods=['POST'])
def clear_data():
    # Validasi input kode rahasia dari form request
    user_key = request.form.get('secret_key', '')
    
    if user_key != SECRET_DELETE_KEY:
        return "Akses Ditolak: Kode rahasia salah atau tidak sah!", 403

    try:
        conn = get_db_connection()
        # 1. Kosongkan tabel data
        conn.execute('DELETE FROM log_hama')
        # 2. Reset Auto-Increment ID kembali ke 1
        conn.execute('DELETE FROM sqlite_sequence WHERE name="log_hama"')
        conn.commit()
        conn.close()

        # 3. Hapus semua berkas gambar fisik di direktori static/uploads/
        for file in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, file)
            if os.path.isfile(file_path) and file != "no_image.jpg":
                os.unlink(file_path)

        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"Gagal membersihkan data: {str(e)}", 500


# ----------------- DASHBOARD UTAMA (FRONT-END HTML & JS) -----------------
@app.route('/', methods=['GET'])
def dashboard():
    conn = get_db_connection()
    
    last_log = conn.execute('SELECT timestamp FROM log_hama ORDER BY id DESC LIMIT 1').fetchone()
    status_device = "OFFLINE"
    if last_log:
        try:
            last_time = datetime.strptime(last_log['timestamp'], '%Y-%m-%d %H:%M:%S')
            diff = (datetime.now() - last_time).total_seconds() / 60
            if diff < 10:
                status_device = "ONLINE"
        except:
            status_device = "ONLINE"

    total_today = conn.execute('''
        SELECT COUNT(*) as total FROM log_hama 
        WHERE pred IN (1,2,3,4) AND date(timestamp) = date('now')
    ''').fetchone()['total']

    latest_hama = conn.execute('''
        SELECT foto_path, pred, timestamp FROM log_hama 
        WHERE pred IN (1,2,3,4) ORDER BY id DESC LIMIT 1
    ''').fetchone()

    # Logika Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    total_rows = conn.execute('SELECT COUNT(*) as total FROM log_hama').fetchone()['total']
    total_pages = math.ceil(total_rows / per_page) if total_rows > 0 else 1

    riwayat = conn.execute('''
        SELECT id, device_id, pred, confidence, lat, arena, ram, foto_path, timestamp 
        FROM log_hama 
        ORDER BY id DESC 
        LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()

    conn.close()

    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <title>Dashboard IoT Smart Pest Monitoring</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f6f9; margin: 0; padding: 20px; color: #333; }
            .container { max-width: 1200px; margin: 0 auto; }
            h1 { text-align: center; color: #2c3e50; margin-bottom: 30px; font-weight: 600; }
            .grid-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center; }
            .card h3 { margin: 0 0 10px 0; color: #7f8c8d; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }
            .card .value { font-size: 28px; font-weight: bold; margin-bottom: 5px; }
            .status-on { color: #2ecc71; } .status-off { color: #e74c3c; }
            .grid-charts { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 30px; }
            @media(max-width: 768px) { .grid-charts { grid-template-columns: 1fr; } }
            .chart-box { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            .latest-photo-box { display: flex; flex-direction: column; align-items: center; justify-content: center; }
            .img-pixelated { width: 130px; height: 130px; image-rendering: pixelated; border: 3px solid #bdc3c7; border-radius: 8px; object-fit: cover; margin-top: 10px; }
            .table-box { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; overflow-x: auto; }
            .table-box h2 { margin-top: 0; color: #2c3e50; font-size: 18px; margin-bottom: 15px; }
            table { width: 100%; border-collapse: collapse; text-align: left; }
            th, td { padding: 12px 15px; border-bottom: 1px solid #eef2f5; font-size: 14px; }
            th { background-color: #f8f9fa; color: #34495e; font-weight: 600; }
            tr:hover { background-color: #fdfefe; }
            .hama-link { color: #3498db; text-decoration: none; font-weight: 600; }
            .hama-link:hover { text-decoration: underline; color: #2980b9; }
            
            .pagination { display: flex; justify-content: center; align-items: center; gap: 5px; margin-top: 20px; }
            .pagination a, .pagination span { padding: 8px 14px; border: 1px solid #dcdde1; border-radius: 6px; text-decoration: none; color: #2f3640; font-size: 14px; }
            .pagination a:hover { background-color: #3498db; color: white; border-color: #3498db; }
            .pagination .active { background-color: #3498db; color: white; border-color: #3498db; font-weight: bold; }
            .pagination .disabled { color: #7f8c8d; background-color: #f5f6fa; cursor: not-allowed; }

            .btn-delete { background-color: #e74c3c; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: bold; display: block; margin: 20px auto 0 auto; transition: background 0.2s; }
            .btn-delete:hover { background-color: #c0392b; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌾 Ekosistem IoT Cerdas - Smart Pest Monitoring 🌾</h1>
            
            <div class="grid-cards">
                <div class="card">
                    <h3>Status Koneksi Node</h3>
                    <div class="value {% if status == 'ONLINE' %}status-on{% else %}status-off{% endif %}">{{ status }}</div>
                    <small>Log terakhir: {{ last_update }}</small>
                </div>
                <div class="card">
                    <h3>Deteksi Hari Ini</h3>
                    <div class="value" style="color: #2c3e50;">{{ today_count }}</div>
                    <small>Seluruh Spesimen Hama 1-4</small>
                </div>
                <div class="card latest-photo-box">
                    <h3>Foto Terakhir Perangkat</h3>
                    {% if latest %}
                        <img class="img-pixelated" src="/static/uploads/{{ latest.foto_path }}" alt="Hama Terakhir">
                        <small style="margin-top:5px; font-weight:bold;">Hama {{ latest.pred }} ({{ (latest.timestamp|string)[11:16] }} WIB)</small>
                    {% else %}
                        <p style="font-size:14px; color:#7f8c8d;">Belum ada data citra</p>
                    {% endif %}
                </div>
            </div>

            <div class="grid-charts">
                <div class="chart-box">
                    <h3 style="margin:0 0 15px 0; font-size:16px; color:#34495e;">Tren Kuantitas Deteksi Hama (7 Hari Terakhir)</h3>
                    <canvas id="lineChart" height="110"></canvas>
                </div>
                <div class="chart-box">
                    <h3 style="margin:0 0 15px 0; font-size:16px; color:#34495e;">Komposisi Jenis Hama</h3>
                    <canvas id="pieChart"></canvas>
                </div>
            </div>

            <div class="table-box">
                <h2>📋 Log Riwayat Deteksi Komprehensif (Total: {{ total_rows }} Data)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Timestamp</th>
                            <th>Node ID</th>
                            <th>Hasil Prediksi AI</th>
                            <th>Confidence</th>
                            <th>Latensi Edge</th>
                            <th>Arena Size</th>
                            <th>Free Heap RAM</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in data_riwayat %}
                        <tr>
                            <td>#{{ row.id }}</td>
                            <td>{{ row.timestamp }}</td>
                            <td><span style="font-family:monospace; background:#f1f2f6; padding:2px 6px; border-radius:4px;">{{ row.device_id }}</span></td>
                            <td>
                                {% if row.pred in [1, 2, 3, 4] %}
                                    <a class="hama-link" href="/static/uploads/{{ row.foto_path }}" target="_blank">🔍 Hama {{ row.pred }}</a>
                                {% else %}
                                    <span style="color:#7f8c8d;">Heartbeat (No Pest)</span>
                                {% endif %}
                            </td>
                            <td>{{ "%.2f"|format(row.confidence) }}</td>
                            <td><strong style="color:#e67e22;">{{ row.lat }} ms</strong></td>
                            <td>{{ row.arena }} KB</td>
                            <td>{{ row.ram }} KB</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>

                <div class="pagination">
                    {% if current_page > 1 %}
                        <a href="/?page={{ current_page - 1 }}">&laquo; Prev</a>
                    {% else %}
                        <span class="disabled">&laquo; Prev</span>
                    {% endif %}

                    {% for p in range(1, total_pages + 1) %}
                        {% if p == current_page %}
                            <span class="active">{{ p }}</span>
                        {% else %}
                            <a href="/?page={{ p }}">{{ p }}</a>
                        {% endif %}
                    {% endfor %}

                    {% if current_page < total_pages %}
                        <a href="/?page={{ current_page + 1 }}">Next &raquo;</a>
                    {% else %}
                        <span class="disabled">Next &raquo;</span>
                    {% endif %}
                </div>
            </div>

            <form id="deleteForm" action="/clear" method="POST" style="display:none;">
                <input type="hidden" name="secret_key" id="secretKeyInput">
            </form>

            <button class="btn-delete" onclick="verifyAndDelete()">🗑️ Clear Data Log</button>
        </div>

        <script>
            // 1. AUTO-REFRESH SETIAP 10 MENIT
            setTimeout(function() {
                window.location.reload();
            }, 600000);

            // 2. LOGIKA PROMPT JAVASCRIPT UNTUK KODE RAHASIA
            function verifyAndDelete() {
                const password = prompt("Masukkan Kode Otentikasi Rahasia Untuk Mengosongkan Basis Data:");
                
                if (password === null) return; // Jika klik cancel
                
                if (password.trim() === "") {
                    alert("Kode rahasia tidak boleh kosong!");
                    return;
                }
                
                // Isi input hidden form dan submit secara aman ke route /clear
                document.getElementById('secretKeyInput').value = password;
                document.getElementById('deleteForm').submit();
            }

            // 3. CHART DATA FETCH
            fetch('/api/hama/statistik')
                .then(response => response.json())
                .then(data => {
                    const ctxLine = document.getElementById('lineChart').getContext('2d');
                    new Chart(ctxLine, {
                        type: 'line',
                        data: {
                            labels: data.line.labels.length > 0 ? data.line.labels : ['Belum Ada Data'],
                            datasets: [{
                                label: 'Jumlah Populasi Terdeteksi',
                                data: data.line.values.length > 0 ? data.line.values : [0],
                                borderColor: '#27ae60',
                                backgroundColor: 'rgba(39, 174, 96, 0.1)',
                                fill: true,
                                tension: 0.3
                            }]
                        },
                        options: { responsive: true }
                    });

                    const ctxPie = document.getElementById('pieChart').getContext('2d');
                    new Chart(ctxPie, {
                        type: 'pie',
                        data: {
                            labels: ['Hama 1', 'Hama 2', 'Hama 3', 'Hama 4'],
                            datasets: [{
                                data: data.pie,
                                backgroundColor: ['#e74c3c', '#f39c12', '#3498db', '#9b59b6']
                            }]
                        },
                        options: { responsive: true }
                    });
                });
        </script>
    </body>
    </html>
    """
    
    return render_template_string(
        HTML_TEMPLATE, 
        status=status_device, 
        today_count=total_today, 
        latest=latest_hama, 
        data_riwayat=riwayat,
        last_update=last_log['timestamp'] if last_log else '-',
        current_page=page,
        total_pages=total_pages,
        total_rows=total_rows
    )

if __name__ == '__main__':
    # Memastikan path database relatif aman di lokal PC maupun cloud
    app.run(debug=True)