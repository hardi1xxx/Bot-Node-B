from flask import Flask, jsonify, request, render_template_string
import gspread
import pandas as pd
import os
import json
import time
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# Cache
cached_df = None
last_fetch_time = 0
CACHE_DURATION = 60

SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "All Node B"

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
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        sheet = None
        for ws in spreadsheet.worksheets():
            if ws.title.strip().upper() == NAMA_SHEET.strip().upper():
                sheet = ws
                break
        if sheet is None:
            return None
        data = sheet.get_all_values()
        if not data or len(data) < 2:
            return None
        df = pd.DataFrame(data[1:], columns=data[0])
        cached_df = df
        last_fetch_time = now
        return df
    except Exception as e:
        print(f"ERROR: {e}")
        return None

@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip().upper()
    if not query:
        return jsonify({"error": "Query kosong"}), 400
    df = get_sheet_data()
    if df is None:
        return jsonify({"error": "Gagal ambil data"}), 500
    result = df[df.iloc[:, 4].astype(str).str.strip().str.upper() == query]
    if result.empty:
        return jsonify({"found": False})
    row = result.iloc[0]
    def safe(idx):
        try:
            v = row.iloc[idx]
            return str(v) if v else "-"
        except:
            return "-"
    return jsonify({
        "found": True,
        "data": {
            "site_id": f"{safe(4)}-{safe(7)}",
            "plan_deploy": safe(1),
            "sub_sistem": safe(3),
            "witel": safe(5),
            "sto": safe(6),
            "status": safe(20),
            "catuan": safe(28),
            "panjang_kabel": safe(29),
            "jenis_kabel": f"{safe(30)} ({safe(31)})",
            "tiang": safe(32),
            "boq": safe(33),
            "ta_area": safe(66),
            "infra": safe(100),
        }
    })

@app.route("/api/dashboard")
def api_dashboard():
    df = get_sheet_data()
    if df is None:
        return jsonify({"error": "Gagal ambil data"}), 500
    total = len(df)
    def count_status(keyword):
        return int(df.iloc[:, 20].astype(str).str.upper().str.contains(keyword, na=False).sum())
    l1_ready = count_status("L1 READY")
    oa_confirm = count_status("OA CONFIRMATION")
    on_progress = count_status("ON PROGRESS")
    done = count_status("DONE")
    statuses = df.iloc[:, 20].astype(str).str.upper().str.strip()
    status_counts = statuses.value_counts().head(8).to_dict()
    recent = []
    for _, row in df.iterrows():
        try:
            site_id = str(row.iloc[4]).strip()
            status = str(row.iloc[20]).strip()
            witel = str(row.iloc[5]).strip()
            if site_id and site_id != "nan" and status and status != "nan":
                recent.append({"site_id": site_id, "status": status, "witel": witel})
        except:
            continue
        if len(recent) >= 50:
            break
    return jsonify({
        "total": total,
        "l1_ready": l1_ready,
        "oa_confirmation": oa_confirm,
        "on_progress": on_progress,
        "done": done,
        "status_counts": status_counts,
        "recent": recent
    })

@app.route("/api/table")
def api_table():
    df = get_sheet_data()
    if df is None:
        return jsonify({"error": "Gagal ambil data"}), 500
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    filter_witel = request.args.get("witel", "").strip().upper()
    filter_status = request.args.get("status", "").strip().upper()
    search = request.args.get("search", "").strip().upper()
    filtered = df.copy()
    if filter_witel:
        filtered = filtered[filtered.iloc[:, 5].astype(str).str.upper().str.contains(filter_witel, na=False)]
    if filter_status:
        filtered = filtered[filtered.iloc[:, 20].astype(str).str.upper().str.contains(filter_status, na=False)]
    if search:
        mask = (
            filtered.iloc[:, 4].astype(str).str.upper().str.contains(search, na=False) |
            filtered.iloc[:, 7].astype(str).str.upper().str.contains(search, na=False) |
            filtered.iloc[:, 5].astype(str).str.upper().str.contains(search, na=False)
        )
        filtered = filtered[mask]
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    page_data = filtered.iloc[start:end]
    rows = []
    for _, row in page_data.iterrows():
        def safe(idx):
            try:
                v = row.iloc[idx]
                return str(v) if v else "-"
            except:
                return "-"
        rows.append({
            "site_id": safe(4),
            "site_name": safe(7),
            "witel": safe(5),
            "sto": safe(6),
            "sub_sistem": safe(3),
            "status": safe(20),
            "plan_deploy": safe(1),
        })
    witels = sorted(df.iloc[:, 5].astype(str).dropna().unique().tolist())
    return jsonify({"total": total, "page": page, "per_page": per_page, "rows": rows, "witels": witels})

HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NODE-B Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root{
  --bg:#0A0F1E;--bg2:#111827;--bg3:#1E293B;--bg4:#243044;
  --accent:#00D4FF;--accent2:#0099BB;--orange:#FF6B35;--green:#22C55E;--yellow:#F59E0B;--red:#EF4444;
  --text:#F0F4FF;--text2:#94A3B8;--text3:#64748B;
  --border:#1E293B;--border2:#243044;
  --card-bg:#111827;--radius:12px;--radius-sm:8px;
}
body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;min-height:100vh;}
.navbar{background:rgba(10,15,30,0.95);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 2rem;height:60px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
.logo{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.2rem;color:var(--accent);letter-spacing:1px;}
.logo span{color:var(--text2);font-weight:400;}
.nav-tabs{display:flex;gap:4px;}
.nav-tab{padding:6px 16px;border-radius:var(--radius-sm);border:none;background:transparent;color:var(--text2);cursor:pointer;font-size:14px;font-family:'Inter',sans-serif;transition:all .2s;}
.nav-tab:hover{background:var(--bg3);color:var(--text);}
.nav-tab.active{background:var(--bg3);color:var(--accent);}
.page{display:none;padding:2rem;max-width:1200px;margin:0 auto;}
.page.active{display:block;}

/* HERO SEARCH */
.hero{text-align:center;padding:3rem 1rem 2rem;}
.hero h1{font-family:'Space Grotesk',sans-serif;font-size:2.5rem;font-weight:700;margin-bottom:.5rem;}
.hero h1 span{color:var(--accent);}
.hero p{color:var(--text2);font-size:1rem;margin-bottom:2rem;}
.search-wrap{position:relative;max-width:560px;margin:0 auto;}
.search-radar{position:absolute;left:-60px;top:50%;transform:translateY(-50%);width:44px;height:44px;border-radius:50%;border:2px solid var(--accent);opacity:.15;animation:radar 2s ease-out infinite;}
.search-radar:nth-child(2){animation-delay:.6s;}
.search-radar:nth-child(3){animation-delay:1.2s;}
@keyframes radar{0%{transform:translateY(-50%) scale(.8);opacity:.3;}100%{transform:translateY(-50%) scale(2);opacity:0;}}
.search-box{width:100%;padding:1rem 1.25rem 1rem 3.2rem;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--radius);font-size:1.1rem;color:var(--text);font-family:'Space Grotesk',sans-serif;outline:none;transition:border-color .2s,box-shadow .2s;}
.search-box:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,212,255,.1);}
.search-icon{position:absolute;left:1rem;top:50%;transform:translateY(-50%);color:var(--text3);font-size:1.1rem;}
.search-btn{margin-top:1rem;padding:.8rem 2.5rem;background:var(--accent);color:#0A0F1E;border:none;border-radius:var(--radius-sm);font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1rem;cursor:pointer;transition:background .2s,transform .1s;}
.search-btn:hover{background:var(--accent2);}
.search-btn:active{transform:scale(.98);}

/* RESULT CARD */
.result-card{margin-top:2rem;background:var(--card-bg);border:1px solid var(--border2);border-radius:var(--radius);padding:1.5rem;animation:fadeIn .3s ease;}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:translateY(0);}}
.result-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:1.25rem;padding-bottom:1rem;border-bottom:1px solid var(--border);}
.result-site-id{font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:700;color:var(--accent);}
.status-badge{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;}
.status-l1{background:rgba(34,197,94,.15);color:#22C55E;border:1px solid rgba(34,197,94,.3);}
.status-oa{background:rgba(245,158,11,.15);color:#F59E0B;border:1px solid rgba(245,158,11,.3);}
.status-progress{background:rgba(0,212,255,.15);color:var(--accent);border:1px solid rgba(0,212,255,.3);}
.status-done{background:rgba(34,197,94,.15);color:#22C55E;border:1px solid rgba(34,197,94,.3);}
.status-default{background:var(--bg3);color:var(--text2);border:1px solid var(--border2);}
.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;}
.result-field{background:var(--bg3);border-radius:var(--radius-sm);padding:12px;}
.field-label{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}
.field-value{font-size:14px;color:var(--text);font-weight:500;}
.error-msg{text-align:center;padding:2rem;color:var(--red);background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);border-radius:var(--radius);}

/* DASHBOARD */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:2rem;}
.stat-card{background:var(--card-bg);border:1px solid var(--border2);border-radius:var(--radius);padding:1.25rem;position:relative;overflow:hidden;}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.stat-card.blue::before{background:var(--accent);}
.stat-card.orange::before{background:var(--orange);}
.stat-card.green::before{background:var(--green);}
.stat-card.yellow::before{background:var(--yellow);}
.stat-card.total::before{background:linear-gradient(90deg,var(--accent),var(--orange));}
.stat-label{font-size:12px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:.5rem;}
.stat-value{font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:700;color:var(--text);}
.stat-card.blue .stat-value{color:var(--accent);}
.stat-card.orange .stat-value{color:var(--orange);}
.stat-card.green .stat-value{color:var(--green);}
.stat-card.yellow .stat-value{color:var(--yellow);}
.section-title{font-family:'Space Grotesk',sans-serif;font-size:1rem;font-weight:600;color:var(--text2);margin-bottom:1rem;text-transform:uppercase;letter-spacing:.5px;}
.recent-table{width:100%;border-collapse:collapse;font-size:13px;}
.recent-table th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--border);color:var(--text3);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px;}
.recent-table td{padding:10px 12px;border-bottom:1px solid var(--border);}
.recent-table tr:hover td{background:var(--bg3);}
.recent-table td:first-child{font-family:'Space Grotesk',sans-serif;font-weight:600;color:var(--accent);}

/* TABLE PAGE */
.filter-bar{display:flex;gap:12px;margin-bottom:1.5rem;flex-wrap:wrap;align-items:center;}
.filter-bar input,.filter-bar select{padding:8px 14px;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--radius-sm);color:var(--text);font-size:13px;font-family:'Inter',sans-serif;outline:none;}
.filter-bar input:focus,.filter-bar select:focus{border-color:var(--accent);}
.filter-bar select option{background:var(--bg2);}
.data-table-wrap{background:var(--card-bg);border:1px solid var(--border2);border-radius:var(--radius);overflow:hidden;}
.data-table{width:100%;border-collapse:collapse;font-size:13px;}
.data-table th{padding:10px 14px;background:var(--bg3);color:var(--text3);text-align:left;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap;}
.data-table td{padding:10px 14px;border-bottom:1px solid var(--border);color:var(--text);}
.data-table tr:hover td{background:var(--bg3);}
.data-table td:first-child{font-family:'Space Grotesk',sans-serif;font-weight:600;color:var(--accent);cursor:pointer;}
.data-table td:first-child:hover{color:#fff;}
.pagination{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-top:1px solid var(--border);font-size:13px;color:var(--text2);}
.pag-btns{display:flex;gap:6px;}
.pag-btn{padding:6px 14px;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--radius-sm);color:var(--text2);cursor:pointer;font-size:13px;font-family:'Inter',sans-serif;transition:all .2s;}
.pag-btn:hover:not(:disabled){background:var(--bg4);color:var(--text);}
.pag-btn:disabled{opacity:.4;cursor:not-allowed;}
.pag-btn.active{background:var(--accent);color:#0A0F1E;border-color:var(--accent);font-weight:600;}
.loading{text-align:center;padding:3rem;color:var(--text2);}
.pulse{display:inline-block;width:8px;height:8px;background:var(--accent);border-radius:50%;animation:pulse 1s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.5;transform:scale(.8);}}
</style>
</head>
<body>

<nav class="navbar">
  <div class="logo">NODE<span>-B</span> DASHBOARD</div>
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="showPage('search')">🔍 Cari Site</button>
    <button class="nav-tab" onclick="showPage('dashboard')">📊 Dashboard</button>
    <button class="nav-tab" onclick="showPage('table')">📋 Semua Data</button>
  </div>
</nav>

<!-- SEARCH PAGE -->
<div id="page-search" class="page active">
  <div class="hero">
    <h1>Cari <span>Site ID</span></h1>
    <p>Masukkan Site ID untuk melihat detail informasi site</p>
    <div class="search-wrap">
      <div class="search-radar"></div>
      <div class="search-radar"></div>
      <div class="search-radar"></div>
      <span class="search-icon">🔍</span>
      <input class="search-box" id="searchInput" type="text" placeholder="Contoh: EPG240" autocomplete="off"
        onkeydown="if(event.key==='Enter')doSearch()">
    </div>
    <br>
    <button class="search-btn" onclick="doSearch()">CARI SITE</button>
  </div>
  <div id="searchResult"></div>
</div>

<!-- DASHBOARD PAGE -->
<div id="page-dashboard" class="page">
  <div style="margin-bottom:1.5rem;">
    <h2 style="font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:700;">Dashboard Status</h2>
    <p style="color:var(--text2);font-size:13px;margin-top:4px;" id="dashLastUpdate">Memuat data...</p>
  </div>
  <div id="statsGrid" class="stats-grid">
    <div class="stat-card total"><div class="stat-label">Total Site</div><div class="stat-value" id="statTotal"><span class="pulse"></span></div></div>
    <div class="stat-card blue"><div class="stat-label">L1 Ready</div><div class="stat-value" id="statL1"><span class="pulse"></span></div></div>
    <div class="stat-card yellow"><div class="stat-label">OA Confirmation</div><div class="stat-value" id="statOA"><span class="pulse"></span></div></div>
    <div class="stat-card orange"><div class="stat-label">On Progress</div><div class="stat-value" id="statProgress"><span class="pulse"></span></div></div>
    <div class="stat-card green"><div class="stat-label">Done</div><div class="stat-value" id="statDone"><span class="pulse"></span></div></div>
  </div>
  <div class="section-title">Data Site Terbaru</div>
  <div class="data-table-wrap">
    <table class="recent-table">
      <thead><tr><th>Site ID</th><th>Witel</th><th>Status</th></tr></thead>
      <tbody id="recentBody"><tr><td colspan="3" class="loading"><span class="pulse"></span> Memuat...</td></tr></tbody>
    </table>
  </div>
</div>

<!-- TABLE PAGE -->
<div id="page-table" class="page">
  <div class="filter-bar">
    <input id="tableSearch" type="text" placeholder="🔍 Cari Site ID / Nama / Witel..." style="flex:1;min-width:200px;" oninput="loadTable(1)">
    <select id="filterWitel" onchange="loadTable(1)"><option value="">Semua Witel</option></select>
    <select id="filterStatus" onchange="loadTable(1)">
      <option value="">Semua Status</option>
      <option>L1 READY</option>
      <option>OA CONFIRMATION</option>
      <option>ON PROGRESS</option>
      <option>DONE</option>
    </select>
  </div>
  <div class="data-table-wrap">
    <table class="data-table">
      <thead><tr>
        <th>Site ID</th><th>Site Name</th><th>Witel</th><th>STO</th><th>Sub Sistem</th><th>Status</th><th>Plan Deploy</th>
      </tr></thead>
      <tbody id="tableBody"><tr><td colspan="7" class="loading"><span class="pulse"></span> Memuat data...</td></tr></tbody>
    </table>
    <div class="pagination">
      <span id="tableInfo" style="color:var(--text3);font-size:12px;"></span>
      <div class="pag-btns" id="pagBtns"></div>
    </div>
  </div>
</div>

<script>
let currentPage = 1;
let dashboardLoaded = false;
let tableLoaded = false;

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'dashboard' && !dashboardLoaded) { loadDashboard(); dashboardLoaded = true; }
  if (name === 'table' && !tableLoaded) { loadTable(1); tableLoaded = true; }
}

function statusBadge(s) {
  const u = s.toUpperCase();
  let cls = 'status-default';
  if (u.includes('L1 READY')) cls = 'status-l1';
  else if (u.includes('OA CONFIRMATION')) cls = 'status-oa';
  else if (u.includes('ON PROGRESS')) cls = 'status-progress';
  else if (u.includes('DONE')) cls = 'status-done';
  return `<span class="status-badge ${cls}">${s}</span>`;
}

async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const el = document.getElementById('searchResult');
  el.innerHTML = '<div class="loading"><span class="pulse"></span> Mencari...</div>';
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q));
    const d = await r.json();
    if (!d.found) {
      el.innerHTML = `<div class="error-msg">❌ Site ID "<strong>${q}</strong>" tidak ditemukan dalam data.</div>`;
      return;
    }
    const data = d.data;
    el.innerHTML = `
    <div class="result-card">
      <div class="result-header">
        <div class="result-site-id">📡 ${data.site_id}</div>
        ${statusBadge(data.status)}
      </div>
      <div class="result-grid">
        <div class="result-field"><div class="field-label">Plan Deploy</div><div class="field-value">${data.plan_deploy}</div></div>
        <div class="result-field"><div class="field-label">Sub Sistem</div><div class="field-value">${data.sub_sistem}</div></div>
        <div class="result-field"><div class="field-label">Witel</div><div class="field-value">${data.witel}</div></div>
        <div class="result-field"><div class="field-label">STO</div><div class="field-value">${data.sto}</div></div>
        <div class="result-field"><div class="field-label">Status Pekerjaan</div><div class="field-value">${data.status}</div></div>
        <div class="result-field"><div class="field-label">Catuan</div><div class="field-value">${data.catuan}</div></div>
        <div class="result-field"><div class="field-label">Panjang Kabel</div><div class="field-value">${data.panjang_kabel}</div></div>
        <div class="result-field"><div class="field-label">Jenis Kabel</div><div class="field-value">${data.jenis_kabel}</div></div>
        <div class="result-field"><div class="field-label">Tiang</div><div class="field-value">${data.tiang}</div></div>
        <div class="result-field"><div class="field-label">Nilai BoQ (Survey)</div><div class="field-value">${data.boq}</div></div>
        <div class="result-field"><div class="field-label">New TA Area</div><div class="field-value">${data.ta_area}</div></div>
        <div class="result-field"><div class="field-label">New Infra / Fiberization</div><div class="field-value">${data.infra}</div></div>
      </div>
    </div>`;
  } catch(e) {
    el.innerHTML = '<div class="error-msg">❌ Gagal menghubungi server.</div>';
  }
}

async function loadDashboard() {
  try {
    const r = await fetch('/api/dashboard');
    const d = await r.json();
    document.getElementById('statTotal').textContent = d.total.toLocaleString();
    document.getElementById('statL1').textContent = d.l1_ready.toLocaleString();
    document.getElementById('statOA').textContent = d.oa_confirmation.toLocaleString();
    document.getElementById('statProgress').textContent = d.on_progress.toLocaleString();
    document.getElementById('statDone').textContent = d.done.toLocaleString();
    document.getElementById('dashLastUpdate').textContent = 'Data diperbarui: ' + new Date().toLocaleString('id-ID');
    const tbody = document.getElementById('recentBody');
    tbody.innerHTML = d.recent.map(row => `
      <tr>
        <td style="cursor:pointer;color:var(--accent);" onclick="searchSite('${row.site_id}')">${row.site_id}</td>
        <td style="color:var(--text2);">${row.witel}</td>
        <td>${statusBadge(row.status)}</td>
      </tr>`).join('');
  } catch(e) {
    document.getElementById('dashLastUpdate').textContent = 'Gagal memuat data.';
  }
}

function searchSite(id) {
  showPage('search');
  document.querySelectorAll('.nav-tab').forEach((t,i) => { if(i===0) t.classList.add('active'); else t.classList.remove('active'); });
  document.getElementById('searchInput').value = id;
  doSearch();
}

let tableTimeout;
async function loadTable(page) {
  clearTimeout(tableTimeout);
  tableTimeout = setTimeout(async () => {
    currentPage = page || 1;
    const search = document.getElementById('tableSearch').value;
    const witel = document.getElementById('filterWitel').value;
    const status = document.getElementById('filterStatus').value;
    const params = new URLSearchParams({page: currentPage, per_page: 20, search, witel, status});
    document.getElementById('tableBody').innerHTML = '<tr><td colspan="7" class="loading"><span class="pulse"></span> Memuat...</td></tr>';
    try {
      const r = await fetch('/api/table?' + params);
      const d = await r.json();
      if (d.witels && document.getElementById('filterWitel').options.length === 1) {
        d.witels.forEach(w => {
          const opt = document.createElement('option');
          opt.value = w; opt.textContent = w;
          document.getElementById('filterWitel').appendChild(opt);
        });
      }
      document.getElementById('tableInfo').textContent = `Menampilkan ${((currentPage-1)*20)+1}–${Math.min(currentPage*20, d.total)} dari ${d.total.toLocaleString()} data`;
      document.getElementById('tableBody').innerHTML = d.rows.map(row => `
        <tr>
          <td onclick="searchSite('${row.site_id}')">${row.site_id}</td>
          <td>${row.site_name}</td>
          <td>${row.witel}</td>
          <td>${row.sto}</td>
          <td>${row.sub_sistem}</td>
          <td>${statusBadge(row.status)}</td>
          <td style="color:var(--text2);">${row.plan_deploy}</td>
        </tr>`).join('');
      const totalPages = Math.ceil(d.total / 20);
      const pagBtns = document.getElementById('pagBtns');
      pagBtns.innerHTML = '';
      const btn = (label, pg, disabled, active) => {
        const b = document.createElement('button');
        b.className = 'pag-btn' + (active ? ' active' : '');
        b.textContent = label;
        b.disabled = disabled;
        if (!disabled) b.onclick = () => loadTable(pg);
        pagBtns.appendChild(b);
      };
      btn('‹', currentPage-1, currentPage===1);
      const start = Math.max(1, currentPage-2), end = Math.min(totalPages, currentPage+2);
      for (let i = start; i <= end; i++) btn(i, i, false, i===currentPage);
      btn('›', currentPage+1, currentPage===totalPages);
    } catch(e) {
      document.getElementById('tableBody').innerHTML = '<tr><td colspan="7" class="error-msg">Gagal memuat data</td></tr>';
    }
  }, 300);
}
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)