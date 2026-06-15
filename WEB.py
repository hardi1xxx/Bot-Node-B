 from flask import Flask, render_template_string, request, jsonify
import gspread
import pandas as pd
import os
import json
import time
from google.oauth2.service_account import Credentials

app = Flask(__name__)

last_fetch_time = 0
cached_df = None
CACHE_DURATION = 30
SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "Node B"

def get_sheet_data():
    global last_fetch_time, cached_df
    now = time.time()
    if cached_df is not None and (now - last_fetch_time < CACHE_DURATION):
        return cached_df
    try:
        credentials_raw = os.getenv("GOOGLE_CREDENTIALS")
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = json.loads(credentials_raw)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(NAMA_SHEET)
        data = sheet.get_all_values()
        df = pd.DataFrame(data)
        headers = df.iloc[0]
        df = df[1:]
        df.columns = headers
        cached_df = df
        last_fetch_time = now
        return df
    except Exception as e:
        print(f"ERROR GOOGLE SHEET: {e}")
        return None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Node B</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px 0;
        }
        .container { max-width: 1200px; }
        .header {
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 { color: #667eea; margin-bottom: 10px; }
        .search-box {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .site-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border-left: 5px solid #667eea;
        }
        .site-card h5 { color: #667eea; margin-bottom: 15px; }
        .site-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }
        .info-item {
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .info-label {
            font-weight: bold;
            color: #667eea;
            font-size: 0.9em;
        }
        .info-value { color: #333; margin-top: 5px; }
        .status-badge {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }
        .status-ready { background: #d4edda; color: #155724; }
        .status-pending { background: #fff3cd; color: #856404; }
        .status-other { background: #e2e3e5; color: #383d41; }
        .btn-search {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            color: white;
        }
        .btn-search:hover {
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            color: white;
        }
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .table-responsive {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        table { margin-bottom: 0; }
        th {
            background: #667eea;
            color: white;
            border: none;
        }
        td { vertical-align: middle; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Dashboard Node B</h1>
            <p class="text-muted">Sistem Monitoring Status Pekerjaan Infrastruktur</p>
        </div>

        <div class="search-box">
            <form method="GET" action="/search" class="row g-3">
                <div class="col-md-8">
                    <input type="text" name="siteid" class="form-control form-control-lg" 
                           placeholder="Masukkan SITEID (contoh: ABC123)" 
                           value="{{ request.args.get('siteid', '') }}">
                </div>
                <div class="col-md-4">
                    <button type="submit" class="btn btn-search btn-lg w-100">🔍 Cari</button>
                </div>
            </form>
        </div>

        {% if error %}
        <div class="error-message">❌ {{ error }}</div>
        {% endif %}

        {% if search_result %}
        <div class="success-message">✅ Data ditemukan</div>
        <div class="site-card">
            <h5>📋 {{ search_result['site_id'] }}</h5>
            <div class="site-info">
                <div class="info-item">
                    <div class="info-label">Plan Deploy</div>
                    <div class="info-value">{{ search_result['plan_deploy'] }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Sub Sistem</div>
                    <div class="info-value">{{ search_result['sub_sistem'] }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Witel & STO</div>
                    <div class="info-value">{{ search_result['witel'] }} ({{ search_result['sto'] }})</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Status Pekerjaan</div>
                    <div class="info-value">
                        <span class="status-badge {% if 'READY' in search_result['status'].upper() %}status-ready{% elif 'CONFIRMATION' in search_result['status'].upper() %}status-pending{% else %}status-other{% endif %}">
                            {{ search_result['status'] }}
                        </span>
                    </div>
                </div>
                <div class="info-item">
                    <div class="info-label">Catuan</div>
                    <div class="info-value">{{ search_result['catuan'] }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Panjang Kabel</div>
                    <div class="info-value">{{ search_result['panjang_kabel'] }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Jenis Kabel</div>
                    <div class="info-value">{{ search_result['jenis_kabel'] }} ({{ search_result['tipe_kabel'] }})</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Tiang</div>
                    <div class="info-value">{{ search_result['tiang'] }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Nilai BoQ (Survey)</div>
                    <div class="info-value">{{ search_result['boq'] }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">New TA AREA</div>
                    <div class="info-value">{{ search_result['ta_area'] }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">NEW INFRA / FIBERIZATION</div>
                    <div class="info-value">{{ search_result['infra'] }}</div>
                </div>
            </div>
        </div>
        {% endif %}

        {% if show_all_sites %}
        <div class="table-responsive">
            <h4 class="mb-4">📑 Semua Site</h4>
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Site ID</th>
                        <th>Plan Deploy</th>
                        <th>Sub Sistem</th>
                        <th>Witel</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for site in all_sites %}
                    <tr>
                        <td><strong>{{ site['site_id'] }}</strong></td>
                        <td>{{ site['plan_deploy'] }}</td>
                        <td>{{ site['sub_sistem'] }}</td>
                        <td>{{ site['witel'] }}</td>
                        <td>
                            <span class="status-badge {% if 'READY' in site['status'].upper() %}status-ready{% elif 'CONFIRMATION' in site['status'].upper() %}status-pending{% else %}status-other{% endif %}">
                                {{ site['status'] }}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/health')
def health():
    return {'status': 'ok'}, 200

@app.route('/')
def index():
    df = get_sheet_data()
    if df is None:
        return render_template_string(HTML_TEMPLATE, error="Gagal mengambil data dari Google Sheets"), 500
    all_sites = []
    for _, row in df.iterrows():
        try:
            all_sites.append({
                'site_id': f"{row.iloc[4]}-{row.iloc[7]}",
                'plan_deploy': row.iloc[1],
                'sub_sistem': row.iloc[3],
                'witel': row.iloc[5],
                'status': row.iloc[20]
            })
        except:
            continue
    return render_template_string(HTML_TEMPLATE, show_all_sites=True, all_sites=all_sites)

@app.route('/search')
def search():
    siteid = request.args.get('siteid', '').strip()
    if not siteid:
        return render_template_string(HTML_TEMPLATE, error="Masukkan SITEID untuk mencari"), 400
    df = get_sheet_data()
    if df is None:
        return render_template_string(HTML_TEMPLATE, error="Gagal mengambil data dari Google Sheets"), 500
    result = df[df.iloc[:, 4].astype(str).str.strip().str.upper() == siteid.upper()]
    if result.empty:
        return render_template_string(HTML_TEMPLATE, error=f"Site ID '{siteid}' tidak ditemukan"), 404
    row = result.iloc[0]
    search_result = {
        'site_id': f"{row.iloc[4]}-{row.iloc[7]}",
        'plan_deploy': row.iloc[1],
        'sub_sistem': row.iloc[3],
        'witel': row.iloc[5],
        'sto': row.iloc[6],
        'status': row.iloc[20],
        'catuan': row.iloc[28],
        'panjang_kabel': row.iloc[29],
        'jenis_kabel': row.iloc[30],
        'tipe_kabel': row.iloc[31],
        'tiang': row.iloc[32],
        'boq': row.iloc[33],
        'ta_area': row.iloc[66],
        'infra': row.iloc[100]
    }
    return render_template_string(HTML_TEMPLATE, search_result=search_result)

@app.route('/api/sites')
def api_sites():
    df = get_sheet_data()
    if df is None:
        return jsonify({'error': 'Gagal mengambil data'}), 500
    sites = []
    for _, row in df.iterrows():
        try:
            sites.append({
                'site_id': f"{row.iloc[4]}-{row.iloc[7]}",
                'plan_deploy': row.iloc[1],
                'sub_sistem': row.iloc[3],
                'witel': row.iloc[5],
                'sto': row.iloc[6],
                'status': row.iloc[20]
            })
        except:
            continue
    return jsonify(sites)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)