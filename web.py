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

SPREADSHEET_ID = "1h1NBs7k4rCibwFvNVu9t0rIlq-TuF7sh6YZvxhu9VqQ"
NAMA_SHEET = "All Node B"


def get_sheet():
    credentials_raw = os.getenv("GOOGLE_CREDENTIALS", "").strip()
    if not credentials_raw:
        print("ERROR: GOOGLE_CREDENTIALS is not set")
        return None
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
    return sheet


def get_sheet_data():
    global last_fetch_time, cached_df
    now = time.time()
    if cached_df is not None and (now - last_fetch_time < CACHE_DURATION):
        return cached_df
    try:
        sheet = get_sheet()
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
    note_text = ""
    try:
        note_text = str(row.iloc[21]) if len(row) > 21 else ""
    except Exception:
        note_text = ""
    return jsonify({
        "found": True,
        "data": {
            "site_id": f"{safe(4)}-{safe(7)}",
            "plan_deploy": safe(1),
            "sub_sistem": safe(3),
            "witel": safe(5),
            "sto": safe(6),
            "status": safe(20),
            "note": note_text,
            "catuan": safe(28),
            "panjang_kabel": safe(29),
            "jenis_kabel": f"{safe(30)} ({safe(31)})",
            "tiang": safe(32),
            "boq": safe(33),
            "ta_area": safe(66),
            "infra": safe(100),
        }
    })

@app.route("/api/update_status", methods=["POST"])
def api_update_status():
    data = request.get_json(silent=True) or {}
    site_id = str(data.get("site_id", "")).strip()
    status = str(data.get("status", "")).strip()
    note = str(data.get("note", "")).strip()
    if not site_id:
        return jsonify({"success": False, "error": "Site ID kosong"}), 400
    if not status:
        return jsonify({"success": False, "error": "Status pekerjaan wajib diisi"}), 400
    if not note:
        return jsonify({"success": False, "error": "Keterangan wajib diisi"}), 400
    try:
        sheet = get_sheet()
        if sheet is None:
            return jsonify({"success": False, "error": "Sheet tidak tersedia"}), 500
        rows = sheet.get_all_values()
        row_index = None
        for idx, row in enumerate(rows[1:], start=2):
            if not row:
                continue
            row_site = str(row[4] if len(row) > 4 else "").strip()
            row_name = str(row[7] if len(row) > 7 else "").strip()
            combined = f"{row_site}-{row_name}" if row_site and row_name else row_site
            if site_id == row_site or site_id == row_name or site_id == combined:
                row_index = idx
                break
        if row_index is None:
            return jsonify({"success": False, "error": "Site ID tidak ditemukan"}), 404
        current_note = str(rows[row_index - 1][21] if len(rows[row_index - 1]) > 21 else "").strip()
        today = time.strftime("%d/%m/%Y")
        new_note = f"{today} : {note}"
        if current_note:
            new_note = f"{new_note}\n{current_note}"
        sheet.update_cell(row_index, 21, status)
        sheet.update_cell(row_index, 22, new_note)
        global cached_df, last_fetch_time
        cached_df = None
        last_fetch_time = 0
        return jsonify({"success": True, "message": "Status dan keterangan berhasil diperbarui"})
    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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

# ==============================
# TREE DIAGRAM (Site ID -> Plan Deploy -> Status Pekerjaan)
# ==============================
def _norm_status(s):
    return " ".join(str(s).strip().upper().split())

HOLD_STATUSES = {_norm_status(x) for x in [
    "0.2 Confirmed Batal by Tsel", "0. HOLD", "0.1 Need Confirm by Tsel"
]}
L1_ONAIR_STATUSES = {_norm_status(x) for x in [
    "7. L3. OA Confirmation", "7. L1 Ready"
]}
DROP_MOM_STATUSES = {_norm_status(x) for x in [
    "0.3 Drop MoM"
]}

def build_tree_data(df):
    site_col = df.iloc[:, 4].astype(str).str.strip()
    valid_mask = (site_col != "") & (site_col.str.lower() != "nan")
    total = int(valid_mask.sum())

    plan_col = df.iloc[:, 1].astype(str).str.strip().replace("", "Lainnya")
    plan_col = plan_col.where(plan_col.str.lower() != "nan", "Lainnya")
    status_col = df.iloc[:, 20].astype(str).str.strip()

    sub_plan = plan_col[valid_mask]
    sub_status = status_col[valid_mask]

    branches = []
    for plan_name in sub_plan.unique().tolist():
        if plan_name == "Lainnya":
            continue  # tidak ditampilkan sesuai permintaan
        mask = sub_plan == plan_name
        count_plan = int(mask.sum())
        statuses_here = sub_status[mask]

        children = []
        if plan_name.strip().upper() == "TIF":
            l1_count = 0
            drop_count = 0
            ny_group_counts = {}
            for raw in statuses_here:
                ns = _norm_status(raw)
                if ns in L1_ONAIR_STATUSES:
                    l1_count += 1
                elif ns in DROP_MOM_STATUSES:
                    drop_count += 1
                else:
                    if not ns or ns == "NAN":
                        continue  # kosong, tidak ditampilkan
                    key = "Hold" if ns in HOLD_STATUSES else raw.strip()
                    ny_group_counts[key] = ny_group_counts.get(key, 0) + 1

            ny_children = [{"name": k, "count": v} for k, v in
                            sorted(ny_group_counts.items(), key=lambda kv: -kv[1])]
            ny_total = sum(ny_group_counts.values())

            children = [
                {"name": "L1 - On Air", "count": l1_count},
                {"name": "NY On Air", "count": ny_total, "children": ny_children},
                {"name": "Drop MOM", "count": drop_count},
            ]

        branches.append({"name": plan_name, "count": count_plan, "children": children})

    branches.sort(key=lambda b: -b["count"])
    return {"total": total, "children": branches}

@app.route("/api/tree")
def api_tree():
    df = get_sheet_data()
    if df is None:
        return jsonify({"error": "Gagal ambil data"}), 500
    return jsonify(build_tree_data(df))

@app.route("/api/tree_list")
def api_tree_list():
    plan = request.args.get("plan", "").strip()
    group = request.args.get("group", "").strip()
    df = get_sheet_data()
    if df is None:
        return jsonify({"error": "Gagal ambil data"}), 500

    site_col = df.iloc[:, 4].astype(str).str.strip()
    valid_mask = (site_col != "") & (site_col.str.lower() != "nan")
    sub = df[valid_mask].copy()

    if plan:
        plan_col_sub = sub.iloc[:, 1].astype(str).str.strip().replace("", "Lainnya")
        plan_col_sub = plan_col_sub.where(plan_col_sub.str.lower() != "nan", "Lainnya")
        sub = sub[plan_col_sub == plan]

    if group:
        def matches(raw):
            ns = _norm_status(raw)
            if group == "Hold":
                return ns in HOLD_STATUSES
            if group == "L1 - On Air":
                return ns in L1_ONAIR_STATUSES
            if group == "Drop MOM":
                return ns in DROP_MOM_STATUSES
            if group == "NY On Air":
                return bool(ns) and ns != "NAN" and ns not in L1_ONAIR_STATUSES and ns not in DROP_MOM_STATUSES
            return ns == _norm_status(group)
        status_col_sub = sub.iloc[:, 20].astype(str)
        sub = sub[status_col_sub.apply(matches)]

    rows = []
    for _, row in sub.iterrows():
        def safe(idx):
            try:
                v = row.iloc[idx]
                return str(v) if v else "-"
            except Exception:
                return "-"
        rows.append({
            "site_id": safe(4), "site_name": safe(7), "witel": safe(5),
            "sto": safe(6), "status": safe(20), "plan_deploy": safe(1),
        })

    return jsonify({"total": len(rows), "rows": rows[:500]})



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
.update-form{margin-top:1.25rem;padding:1rem;border:1px solid var(--border2);border-radius:var(--radius-sm);background:rgba(255,255,255,0.03);}
.update-form-title{font-size:12px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:.75rem;}
.update-form input,.update-form select,.update-form textarea{width:100%;padding:10px 12px;border:1px solid var(--border2);border-radius:var(--radius-sm);background:var(--bg3);color:var(--text);font-size:14px;font-family:'Inter',sans-serif;margin-bottom:.75rem;}
.update-form select option{background:var(--bg2);color:var(--text);}
.update-form textarea{min-height:90px;resize:vertical;}
.update-form button{padding:.7rem 1rem;border:none;border-radius:var(--radius-sm);background:var(--accent);color:#0A0F1E;font-weight:700;cursor:pointer;}
.update-form button:hover{background:var(--accent2);} 
.update-form .hint{font-size:12px;color:var(--text3);margin-top:.4rem;}
.update-form .note-block{margin-top:.75rem;padding-top:.75rem;border-top:1px solid var(--border2);} 
.status-l1{background:rgba(34,197,94,.15);color:#22C55E;border:1px solid rgba(34,197,94,.3);}
.status-oa{background:rgba(245,158,11,.15);color:#F59E0B;border:1px solid rgba(245,158,11,.3);}
.status-progress{background:rgba(0,212,255,.15);color:var(--accent);border:1px solid rgba(0,212,255,.3);}
.status-done{background:rgba(34,197,94,.15);color:#22C55E;border:1px solid rgba(34,197,94,.3);}
.status-default{background:var(--bg3);color:var(--text2);border:1px solid var(--border2);}
.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;}
.result-field{background:var(--bg3);border-radius:var(--radius-sm);padding:12px;}
.result-field.full{grid-column:1 / -1;}
.field-label{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}
.field-value{font-size:14px;color:var(--text);font-weight:500;white-space:pre-wrap;word-break:break-word;}
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

/* TREE DIAGRAM (horizontal, top-down, classic connector-line style) */
.tree-diagram{overflow-x:auto;overflow-y:hidden;padding:2rem 1rem;}
.tree{display:inline-block;min-width:100%;}
.tree ul{padding-top:20px;position:relative;display:flex;justify-content:center;}
.tree li{list-style:none;text-align:center;position:relative;padding:20px 10px 0 10px;}
.tree li::before,.tree li::after{content:'';position:absolute;top:0;right:50%;border-top:2px solid var(--border2);width:50%;height:20px;}
.tree li::after{right:auto;left:50%;border-left:2px solid var(--border2);}
.tree li:only-child::after,.tree li:only-child::before{display:none;}
.tree li:only-child{padding-top:0;}
.tree li:first-child::before,.tree li:last-child::after{border:0 none;}
.tree li:last-child::before{border-right:2px solid var(--border2);border-radius:0 6px 0 0;}
.tree li:first-child::after{border-radius:6px 0 0 0;}
.tree ul ul::before{content:'';position:absolute;top:0;left:50%;border-left:2px solid var(--border2);width:0;height:20px;}
.tree-node{display:inline-block;background:var(--card-bg);border:1px solid var(--border2);border-radius:var(--radius-sm);padding:10px 16px;min-width:150px;text-align:center;cursor:pointer;transition:transform .15s,border-color .15s;}
.tree-node:hover{transform:translateY(-2px);border-color:var(--accent);}
.tree-node .tn-label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;}
.tree-node .tn-name{font-family:'Space Grotesk',sans-serif;font-size:13px;font-weight:600;color:var(--text);margin-top:2px;white-space:nowrap;}
.tree-node .tn-value{font-family:'Space Grotesk',sans-serif;font-size:1.25rem;font-weight:700;margin-top:2px;}
.tree-node.root{background:var(--bg4);border-color:var(--accent);border-width:2px;}
.tree-node.root .tn-value{color:var(--accent);}
.tree-node.plan{border-color:var(--accent2);}
.tree-node.plan .tn-value{color:var(--accent);}
.tree-node.stat-hold{border-color:var(--red);}
.tree-node.stat-hold .tn-value{color:var(--red);}
.tree-node.stat-onair{border-color:var(--green);}
.tree-node.stat-onair .tn-value{color:var(--green);}
.tree-node.stat-drop{border-color:var(--orange);}
.tree-node.stat-drop .tn-value{color:var(--orange);}
.tree-node.stat-nyonair{border-color:var(--accent);}
.tree-node.stat-nyonair .tn-value{color:var(--accent);}
.tree-node.stat-default{border-color:var(--border2);}
.tree-node.stat-default .tn-value{color:var(--text2);}

/* MODAL (klik node -> list data) */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:1000;align-items:center;justify-content:center;padding:2rem;}
.modal-overlay.active{display:flex;}
.modal-box{background:var(--card-bg);border:1px solid var(--border2);border-radius:var(--radius);max-width:720px;width:100%;max-height:80vh;display:flex;flex-direction:column;animation:fadeIn .2s ease;}
.modal-header{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1.25rem;border-bottom:1px solid var(--border);}
.modal-title{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.05rem;}
.modal-close{background:transparent;border:none;color:var(--text2);font-size:1.3rem;line-height:1;cursor:pointer;padding:4px;}
.modal-close:hover{color:var(--text);}
.modal-body{padding:1rem 1.25rem;overflow-y:auto;}
</style>
</head>
<body>

<nav class="navbar">
  <div class="logo">NODE<span>-B</span> DASHBOARD</div>
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="showPage('search')">🔍 Cari Site</button>
    <button class="nav-tab" onclick="showPage('dashboard')">📊 Dashboard</button>
    <button class="nav-tab" onclick="showPage('table')">📋 Semua Data</button>
    <button class="nav-tab" onclick="showPage('tree')">🌳 Tree Diagram</button>
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

<!-- TREE DIAGRAM PAGE -->
<div id="page-tree" class="page">
  <div style="margin-bottom:1.5rem;">
    <h2 style="font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:700;">Tree Diagram Progress</h2>
    <p style="color:var(--text2);font-size:13px;margin-top:4px;">Total Site → Plan Deploy → Status Pekerjaan. Klik kotak untuk lihat daftar datanya.</p>
  </div>
  <div id="treeContainer" class="tree-diagram"></div>
</div>

<!-- MODAL DETAIL -->
<div id="treeModal" class="modal-overlay" onclick="if(event.target===this) closeTreeModal()">
  <div class="modal-box">
    <div class="modal-header">
      <div id="modalTitle" class="modal-title">Detail</div>
      <button class="modal-close" onclick="closeTreeModal()">✕</button>
    </div>
    <div id="modalBody" class="modal-body"></div>
  </div>
</div>

<script>
let currentPage = 1;
let dashboardLoaded = false;
let tableLoaded = false;
let treeLoaded = false;

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'dashboard' && !dashboardLoaded) { loadDashboard(); dashboardLoaded = true; }
  if (name === 'table' && !tableLoaded) { loadTable(1); tableLoaded = true; }
  if (name === 'tree' && !treeLoaded) { loadTree(); treeLoaded = true; }
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
    const currentNote = data.note ? data.note.replace(/\n/g, '<br>') : '-';
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
        <div class="result-field full"><div class="field-label">Catatan Kolom V</div><div class="field-value">${currentNote}</div></div>
      </div>
      <div class="update-form">
        <div class="update-form-title">Update Status & Catatan</div>
        <select id="updateStatus">
          <option value="">-- Pilih status --</option>
          <option value="0. HOLD">0. HOLD</option>
          <option value="0.1 Proposed Drop">0.1 Proposed Drop</option>
          <option value="0.2 L0 Drop">0.2 L0 Drop</option>
          <option value="0.3 Drop MoM">0.3 Drop MoM</option>
          <option value="1. L0 Survey">1. L0 Survey</option>
          <option value="1.1 Done Survey">1.1 Done Survey</option>
          <option value="2. L0 DRM">2. L0 DRM</option>
          <option value="3. L0 Progress Perizinan">3. L0 Progress Perizinan</option>
          <option value="4. L0 Material Delivery">4. L0 Material Delivery</option>
          <option value="5.0 L0 Progress FO">5.0 L0 Progress FO</option>
          <option value="6. L0 Ready">6. L0 Ready</option>
          <option value="7. L1 Ready">7. L1 Ready</option>
          <option value="7. L3. OA Confirmation">7. L3. OA Confirmation</option>
          <option value="5.1 L0 Progress - Issue BTS">5.1 L0 Progress - Issue BTS</option>
          <option value="0.1 Need Confirm by Tsel">0.1 Need Confirm by Tsel</option>
          <option value="0.2 Confirmed Batal by Tsel">0.2 Confirmed Batal by Tsel</option>
        </select>
        <div class="note-block">
          <textarea id="updateNote" placeholder="Contoh: 02/08/2026 : keterangan baru"></textarea>
        </div>
        <button onclick="submitUpdate('${data.site_id}')">Simpan Perubahan</button>
        <div id="updateMessage" class="hint">Catatan akan ditambahkan ke atas dengan format tanggal otomatis.</div>
      </div>
    </div>`;
  } catch(e) {
    el.innerHTML = '<div class="error-msg">❌ Gagal menghubungi server.</div>';
  }
}

async function submitUpdate(siteId) {
  const statusInput = document.getElementById('updateStatus');
  const noteInput = document.getElementById('updateNote');
  const message = document.getElementById('updateMessage');
  if (!statusInput || !noteInput) return;
  const status = statusInput.value.trim();
  const note = noteInput.value.trim();
  if (!status || !note) {
    message.innerHTML = '<span style="color:#F59E0B;">Status dan keterangan harus diisi.</span>';
    return;
  }
  message.innerHTML = 'Menyimpan...';
  try {
    const r = await fetch('/api/update_status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({site_id: siteId, status, note})
    });
    const d = await r.json();
    if (d.success) {
      message.innerHTML = '<span style="color:#22C55E;">Berhasil disimpan ke kolom status dan kolom V.</span>';
      doSearch();
    } else {
      message.innerHTML = `<span style="color:#EF4444;">${d.error || 'Gagal menyimpan.'}</span>`;
    }
  } catch (e) {
    message.innerHTML = '<span style="color:#EF4444;">Gagal menghubungi server.</span>';
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

function escAttr(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function treeNodeClass(depth, name) {
  if (depth === 0) return 'tree-node root';
  if (depth === 1) return 'tree-node plan';
  const n = (name || '').toUpperCase();
  if (n === 'HOLD') return 'tree-node stat-hold';
  if (n === 'L1 - ON AIR') return 'tree-node stat-onair';
  if (n === 'DROP MOM') return 'tree-node stat-drop';
  if (n === 'NY ON AIR') return 'tree-node stat-nyonair';
  return 'tree-node stat-default';
}

function renderTreeNode(node, depth, planName) {
  const cls = treeNodeClass(depth, node.name);
  const label = depth === 0 ? 'Site ID' : (depth === 1 ? 'Plan Deploy' : '');
  const thisPlan = depth === 0 ? '' : (depth === 1 ? node.name : planName);
  const thisGroup = depth >= 2 ? node.name : '';
  const modalLabel = depth === 0 ? 'Total Semua Site'
    : depth === 1 ? `Plan Deploy: ${node.name}`
    : `${node.name} (Plan Deploy: ${thisPlan})`;
  let html = `<li><div class="${cls}" data-plan="${escAttr(thisPlan)}" data-group="${escAttr(thisGroup)}" data-label="${escAttr(modalLabel)}">
      ${label ? `<div class="tn-label">${label}</div>` : ''}
      <div class="tn-name">${node.name}</div>
      <div class="tn-value">${node.count.toLocaleString()}</div>
    </div>`;
  if (node.children && node.children.length) {
    const nextPlan = depth === 1 ? node.name : planName;
    html += `<ul>` + node.children.map(c => renderTreeNode(c, depth + 1, nextPlan)).join('') + `</ul>`;
  }
  html += `</li>`;
  return html;
}

async function loadTree() {
  const el = document.getElementById('treeContainer');
  el.innerHTML = '<div class="loading"><span class="pulse"></span> Memuat diagram...</div>';
  try {
    const r = await fetch('/api/tree');
    const d = await r.json();
    if (d.error) {
      el.innerHTML = `<div class="error-msg">❌ ${d.error}</div>`;
      return;
    }
    const rootNode = { name: 'Total', count: d.total, children: d.children };
    el.innerHTML = `<div class="tree"><ul>${renderTreeNode(rootNode, 0, null)}</ul></div>`;
    el.querySelectorAll('.tree-node').forEach(node => {
      node.addEventListener('click', () => {
        openTreeDetail(node.dataset.plan || '', node.dataset.group || '', node.dataset.label || '');
      });
    });
  } catch (e) {
    el.innerHTML = '<div class="error-msg">❌ Gagal memuat diagram.</div>';
  }
}

async function openTreeDetail(plan, group, label) {
  document.getElementById('modalTitle').textContent = label;
  document.getElementById('modalBody').innerHTML = '<div class="loading"><span class="pulse"></span> Memuat...</div>';
  document.getElementById('treeModal').classList.add('active');
  const params = new URLSearchParams();
  if (plan) params.set('plan', plan);
  if (group) params.set('group', group);
  try {
    const r = await fetch('/api/tree_list?' + params.toString());
    const d = await r.json();
    if (d.error) {
      document.getElementById('modalBody').innerHTML = `<div class="error-msg">❌ ${d.error}</div>`;
      return;
    }
    if (!d.rows.length) {
      document.getElementById('modalBody').innerHTML = '<div class="loading">Tidak ada data.</div>';
      return;
    }
    const info = d.total > d.rows.length
      ? `Menampilkan ${d.rows.length} dari ${d.total.toLocaleString()} data`
      : `${d.total.toLocaleString()} data`;
    document.getElementById('modalBody').innerHTML = `
      <p style="color:var(--text2);font-size:12px;margin-bottom:.75rem;">${info}</p>
      <table class="data-table"><thead><tr><th>Site ID</th><th>Site Name</th><th>Witel</th><th>Status</th></tr></thead>
      <tbody>` + d.rows.map(row => `
        <tr>
          <td onclick="closeTreeModal();searchSite('${row.site_id}')">${row.site_id}</td>
          <td>${row.site_name}</td>
          <td style="color:var(--text2);">${row.witel}</td>
          <td>${statusBadge(row.status)}</td>
        </tr>`).join('') + `</tbody></table>`;
  } catch (e) {
    document.getElementById('modalBody').innerHTML = '<div class="error-msg">❌ Gagal memuat data.</div>';
  }
}

function closeTreeModal() {
  document.getElementById('treeModal').classList.remove('active');
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

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)