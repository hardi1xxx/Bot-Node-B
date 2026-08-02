import telebot
from telebot import types
import gspread
import pandas as pd
import os
import json
import time
import threading
from google.oauth2.service_account import Credentials

# ==============================
# PERSISTENT STORAGE
# Disimpan ke 2 tempat (prioritas: Volume > Google Sheet > sementara):
# 1. Railway Volume di /data (PERMANEN, tidak hilang saat redeploy, milik service sendiri)
# 2. Tab "Bot State" di Google Sheet (PERMANEN juga, tapi butuh akses Editor ke sheet)
# Kalau Volume belum di-setup di Railway, otomatis fallback ke folder lokal (hilang saat redeploy).
# ==============================
VOLUME_DIR = "/data"
STATE_FILE = os.path.join(VOLUME_DIR, "bot_state.json") if os.path.isdir(VOLUME_DIR) else "bot_state.json"
STATE_SHEET_NAME = "Bot State"

_gsheet_client = None
_state_save_lock = threading.Lock()
_last_sheet_save = 0
_sheet_permission_denied = False
SHEET_SAVE_THROTTLE = 5  # minimal jarak antar save ke Google Sheet (detik)

print(f"💾 Lokasi penyimpanan state file: {STATE_FILE} {'(Railway Volume - permanen)' if os.path.isdir(VOLUME_DIR) else '(folder lokal - HILANG saat redeploy, setup Volume di Railway!)'}")

def get_gsheet_client():
    global _gsheet_client
    if _gsheet_client is not None:
        return _gsheet_client
    try:
        credentials_raw = os.getenv("GOOGLE_CREDENTIALS")
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = json.loads(credentials_raw)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        _gsheet_client = gspread.authorize(creds)
        return _gsheet_client
    except Exception as e:
        print(f"⚠️ Gagal buat Google Sheet client untuk state: {e}")
        return None

def get_or_create_state_sheet():
    """Ambil tab 'Bot State'. Kalau belum ada, buat baru."""
    global _sheet_permission_denied
    if _sheet_permission_denied:
        return None
    client = get_gsheet_client()
    if client is None:
        return None
    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        for ws in spreadsheet.worksheets():
            if ws.title.strip().upper() == STATE_SHEET_NAME.upper():
                return ws
        # Belum ada -> buat baru
        ws = spreadsheet.add_worksheet(title=STATE_SHEET_NAME, rows=10, cols=2)
        ws.update("A1", "key")
        ws.update("B1", "value")
        print(f"✅ Tab '{STATE_SHEET_NAME}' dibuat otomatis di spreadsheet.")
        return ws
    except Exception as e:
        if "PERMISSION_DENIED" in str(e) or "403" in str(e):
            _sheet_permission_denied = True
            print(f"⚠️ Tidak ada izin akses tulis ke spreadsheet (View-only). "
                  f"Lewati Google Sheet, pakai Railway Volume saja.")
        else:
            print(f"⚠️ Gagal akses/buat tab '{STATE_SHEET_NAME}': {e}")
        return None

def load_state_from_sheet():
    """Load state dari Google Sheet. Return None kalau gagal/belum ada data."""
    ws = get_or_create_state_sheet()
    if ws is None:
        return None
    try:
        cell = ws.acell("B2").value
        if not cell:
            return None
        data = json.loads(cell)
        return (
            set(data.get("user_chats", [])),
            data.get("last_status", {}),
            set(data.get("sent_history", [])),
        )
    except Exception as e:
        print(f"⚠️ Gagal load state dari Google Sheet: {e}")
        return None

def save_state_to_sheet(force=False):
    """Simpan state ke Google Sheet, dengan throttle supaya tidak kena rate limit."""
    global _last_sheet_save, _sheet_permission_denied
    if _sheet_permission_denied:
        return  # Sudah tahu tidak ada izin, jangan coba-coba terus (hindari spam log)
    now = time.time()
    if not force and (now - _last_sheet_save < SHEET_SAVE_THROTTLE):
        return
    ws = get_or_create_state_sheet()
    if ws is None:
        return
    try:
        payload = json.dumps({
            "user_chats": list(user_chats),
            "last_status": last_status,
            "sent_history": list(sent_history),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        ws.update("A2", "state_json")
        ws.update("B2", payload)
        _last_sheet_save = now
    except Exception as e:
        if "PERMISSION_DENIED" in str(e) or "403" in str(e):
            _sheet_permission_denied = True
            print(f"⚠️ Tidak ada izin tulis ke Google Sheet (akses View-only). "
                  f"State akan disimpan ke Railway Volume saja. "
                  f"Minta akses Editor ke pemilik sheet untuk mengaktifkan cadangan ganda.")
        else:
            print(f"⚠️ Gagal simpan state ke Google Sheet: {e}")

def load_state_from_file():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return (
                    set(data.get("user_chats", [])),
                    data.get("last_status", {}),
                    set(data.get("sent_history", [])),
                )
        except Exception as e:
            print(f"⚠️ Gagal load state dari file lokal: {e}")
    return None

def save_state_to_file():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "user_chats": list(user_chats),
                "last_status": last_status,
                "sent_history": list(sent_history),
            }, f)
    except Exception as e:
        print(f"⚠️ Gagal simpan state ke file lokal: {e}")

def load_state():
    """
    Prioritas: file di Railway Volume (kalau ada & terbaru) > Google Sheet > kosong.
    Volume jadi sumber utama karena tidak bergantung pada izin akses Google Sheet
    (yang mungkin cuma View-only). Google Sheet tetap dicoba sebagai pelengkap/cadangan.
    """
    file_state = load_state_from_file()
    if file_state is not None and os.path.isdir(VOLUME_DIR):
        print("📂 State dimuat dari Railway Volume (sumber permanen utama).")
        # Tetap coba sinkron ke Google Sheet kalau memungkinkan (silent, tidak blocking)
        return file_state

    sheet_state = load_state_from_sheet()
    if sheet_state is not None:
        print("📂 State dimuat dari Google Sheet.")
        return sheet_state

    if file_state is not None:
        print("📂 State dimuat dari file lokal (sementara, akan hilang saat redeploy).")
        return file_state

    print("📂 Tidak ada state tersimpan, mulai dari kosong.")
    return set(), {}, set()

def save_state(force=False):
    """Simpan ke kedua tempat sekaligus."""
    with _state_save_lock:
        save_state_to_file()
        save_state_to_sheet(force=force)

# ==============================
# GLOBAL VARIABLE
# ==============================
SPREADSHEET_ID = "1h1NBs7k4rCibwFvNVu9t0rIlq-TuF7sh6YZvxhu9VqQ"

user_chats, last_status, sent_history = load_state()
last_fetch_time = 0
cached_df = None
# first_run cuma True kalau memang belum ada history tersimpan sama sekali (deploy pertama kali).
# Kalau ini redeploy dan state lama berhasil dimuat, first_run harus False supaya perubahan
# status yang terjadi SAAT bot mati (proses redeploy) tetap terdeteksi & dinotifikasi,
# bukan dianggap "baseline baru" lalu di-skip.
first_run = (len(last_status) == 0)
CACHE_DURATION = 30

print(f"📂 State siap: {len(user_chats)} chat, {len(last_status)} site dipantau, {len(sent_history)} histori notif")

# ==============================
# CONFIG
# ==============================
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN tidak ditemukan!")

NAMA_SHEET = "All Node B"

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://bot-node-b-web-bghh-production.up.railway.app")

bot = telebot.TeleBot(TOKEN)

# Jika ingin mematikan notifikasi otomatis sementara, set DISABLE_NOTIFICATIONS=1/true/yes
DISABLE_NOTIFICATIONS = os.getenv("DISABLE_NOTIFICATIONS", "false").lower() in ("1", "true", "yes", "y")
if DISABLE_NOTIFICATIONS:
    print("🔕 Notifikasi otomatis DISABLED oleh variabel lingkungan DISABLE_NOTIFICATIONS")

# Jika ingin sepenuhnya menghapus/menonaktifkan notifikasi perubahan status,
# set DISABLE_STATUS_NOTIFICATIONS=1/true/yes di environment.
DISABLE_STATUS_NOTIFICATIONS = os.getenv("DISABLE_STATUS_NOTIFICATIONS", "false").lower() in ("1", "true", "yes", "y")
if DISABLE_STATUS_NOTIFICATIONS:
    print("🔕 Notifikasi PERUBAHAN STATUS dinonaktifkan oleh variabel lingkungan DISABLE_STATUS_NOTIFICATIONS")

# ==============================
# NORMALISASI STATUS
# ==============================
def clean_status(s):
    return " ".join(str(s).upper().replace(".", "").split())

# ==============================
# CONNECT GOOGLE SHEET (CACHE)
# ==============================
def get_sheet_data():
    global last_fetch_time, cached_df

    now = time.time()

    if cached_df is not None and (now - last_fetch_time < CACHE_DURATION):
        return cached_df

    try:
        client = get_gsheet_client()
        if client is None:
            raise ValueError("Gagal membuat Google Sheet client.")

        spreadsheet = client.open_by_key(SPREADSHEET_ID)

        sheet = None
        for ws in spreadsheet.worksheets():
            ws_title = ws.title.strip()
            if ws_title.upper() == NAMA_SHEET.strip().upper():
                sheet = ws
                break

        if sheet is None:
            available = [ws.title for ws in spreadsheet.worksheets()]
            raise ValueError(
                f"Sheet '{NAMA_SHEET}' tidak ditemukan! "
                f"Sheet yang tersedia: {available}"
            )

        data = sheet.get_all_values()

        if not data or len(data) < 2:
            raise ValueError("Sheet kosong atau hanya berisi header!")

        df = pd.DataFrame(data[1:], columns=data[0])

        cached_df = df
        last_fetch_time = now

        return df

    except Exception as e:
        print(f"ERROR GOOGLE SHEET: {e}")
        return None

def make_markup(chat_type):
    markup = types.InlineKeyboardMarkup()
    if chat_type == "private":
        markup.add(types.InlineKeyboardButton(
            "📡 Buka Dashboard",
            web_app=types.WebAppInfo(url=WEBAPP_URL)
        ))
    else:
        markup.add(types.InlineKeyboardButton(
            "📡 Buka Dashboard",
            url=WEBAPP_URL
        ))
    return markup

# ==============================
# COMMAND START
# ==============================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_chats.add(message.chat.id)
    save_state(force=True)
    print(f"✅ Chat {message.chat.id} ({message.chat.type}) terdaftar untuk notifikasi. Total: {len(user_chats)}")

    markup = make_markup(message.chat.type)
    bot.reply_to(
        message,
        "✅ Bot aktif!\nGunakan:\n/cari SITEID\n\nAtau buka dashboard lengkap di bawah ini:",
        reply_markup=markup
    )

# ==============================
# COMMAND CARI
# ==============================
@bot.message_handler(commands=['cari'])
def search_site(message):
    try:
        site_id_cari = message.text.split(maxsplit=1)[1].strip()
    except IndexError:
        bot.reply_to(message, "Gunakan:\n/cari SITEID")
        return

    df = get_sheet_data()

    if df is None:
        bot.reply_to(message, "❌ Gagal ambil data dari Google Sheet.")
        return

    result = df[df.iloc[:, 4].astype(str).str.strip().str.upper() == site_id_cari.upper()]

    if result.empty:
        bot.reply_to(message, f"❌ Site ID '{site_id_cari}' tidak ditemukan.")
        return

    row = result.iloc[0]

    def safe(idx):
        try:
            return row.iloc[idx]
        except Exception:
            return "-"

    response = f"""
<b>📋 DATA SITE</b>
━━━━━━━━━━━━━━━

<b>Site ID :</b> {safe(4)}-{safe(7)}
<b>Plan Deploy :</b> {safe(1)}
<b>Sub Sistem :</b> {safe(3)}
<b>Witel &amp; STO :</b> {safe(5)} ({safe(6)})
<b>Status Pekerjaan :</b> {safe(20)}
<b>Catuan :</b> {safe(28)}
<b>Panjang Kabel :</b> {safe(29)}
<b>Jenis Kabel :</b> {safe(30)} ({safe(31)})
<b>Tiang :</b> {safe(32)}
<b>Nilai BoQ (Survey) :</b> {safe(33)}
<b>New TA AREA :</b> {safe(66)}
<b>NEW INFRA / FIBERIZATION :</b> {safe(100)}
    """

    markup = make_markup(message.chat.type)
    bot.reply_to(message, response, parse_mode='HTML', reply_markup=markup)

# ==============================
# DASHBOARD NOTIF
# ==============================
def send_dashboard(changes_list):
    if not changes_list:
        return

    if DISABLE_NOTIFICATIONS:
        print("🔕 Notifikasi otomatis dimatikan; melewatkan pengiriman dashboard.")
        return

    if not user_chats:
        print("⚠️ Tidak ada chat terdaftar (user_chats kosong). Notifikasi tidak terkirim ke siapapun.")
        print("   → Pastikan minimal 1 user/grup pernah kirim /start ke bot.")
        return

    message = "<b>🚨 UPDATE STATUS (DASHBOARD)</b>\n━━━━━━━━━━━━━━━\n\n"

    for row in changes_list:
        try:
            message += (
                f"<b>{row.iloc[4]}-{row.iloc[7]}</b>\n"
                f"Status : {row.iloc[20]}\n"
                f"Witel  : {row.iloc[5]}\n\n"
            )
        except Exception:
            continue

    message += f"\nTotal Update: {len(changes_list)}"

    success_count = 0
    for chat_id in list(user_chats):
        try:
            try:
                chat = bot.get_chat(chat_id)
                chat_type = chat.type
            except Exception:
                chat_type = "private"

            markup = make_markup(chat_type)
            bot.send_message(chat_id, message, parse_mode='HTML', reply_markup=markup)
            success_count += 1
        except Exception as e:
            print(f"❌ Gagal kirim ke chat {chat_id}: {e}")
            if "blocked" in str(e).lower() or "kicked" in str(e).lower() or "chat not found" in str(e).lower():
                user_chats.discard(chat_id)
                print(f"   → Chat {chat_id} dihapus dari daftar (bot diblokir/dikeluarkan).")

    save_state(force=True)
    print(f"📨 Notifikasi terkirim ke {success_count} chat.")

# ==============================
# MONITORING STATUS
# ==============================
def check_status_changes():
    global last_status, first_run

    df = get_sheet_data()
    if df is None:
        print("⚠️ check_status_changes: data sheet kosong/gagal, skip cycle ini.")
        return

    changes_list = []
    state_changed = False

    # Jika notifikasi perubahan status dinonaktifkan, kita tetap update `last_status`
    # supaya state internal sinkron, tetapi tidak menambahkan ke `changes_list`
    # dan tidak mengirim notifikasi.
    if DISABLE_STATUS_NOTIFICATIONS:
        for _, row in df.iterrows():
            try:
                site_id = str(row.iloc[4]).strip()
                if not site_id or site_id == "nan":
                    continue

                status = clean_status(row.iloc[20])

                # Set last_status ketika belum ada atau berubah, tanpa notif
                if site_id not in last_status or last_status[site_id] != status:
                    last_status[site_id] = status
                    state_changed = True
            except Exception as e:
                print(f"ERROR LOOP (silent update): {e}")
                continue

        if state_changed:
            save_state()
        return

    for _, row in df.iterrows():
        try:
            site_id = str(row.iloc[4]).strip()
            if not site_id or site_id == "nan":
                continue

            status = clean_status(row.iloc[20])

            if site_id not in last_status:
                last_status[site_id] = status
                state_changed = True
                continue

            if last_status[site_id] == status:
                continue

            old_status = last_status[site_id]
            last_status[site_id] = status
            state_changed = True

            print(f"[STATUS] {site_id} | {old_status} → {status}")

            # Site ini baru saja KELUAR dari status yang pernah dinotifikasi (L1 READY / OA CONFIRMATION).
            # Hapus riwayat kirim lamanya, supaya kalau nanti dia MASUK LAGI ke status itu
            # (misal sempat di-revert lalu di-confirm ulang), dianggap kejadian baru & dinotifikasi lagi.
            if ("L1 READY" in old_status) or ("OA CONFIRMATION" in old_status):
                stale_keys = {k for k in sent_history if k.startswith(f"{site_id}|")}
                if stale_keys:
                    sent_history.difference_update(stale_keys)
                    state_changed = True
                    print(f"   → {site_id} keluar dari status ternotifikasi, riwayat kirim di-reset ({len(stale_keys)} entri).")

            if first_run:
                continue

            key = f"{site_id}|{status}"

            if ("L1 READY" in status) or ("OA CONFIRMATION" in status):
                if key in sent_history:
                    print(f"   → {key} sudah pernah dikirim, skip.")
                    continue
                changes_list.append(row)
                sent_history.add(key)
                state_changed = True

        except Exception as e:
            print(f"ERROR LOOP: {e}")
            continue

    if state_changed:
        save_state()

    if changes_list:
        send_dashboard(changes_list)
        print(f"✅ Notif dashboard: {len(changes_list)} perubahan status dikirim.")

# ==============================
# SCHEDULER
# ==============================
def run_scheduler():
    global first_run

    while True:
        try:
            check_status_changes()
        except Exception as e:
            print(f"❌ ERROR di scheduler: {e}")

        if first_run:
            first_run = False
            print("✅ First run selesai. Monitoring aktif — perubahan status mulai sekarang akan dinotifikasi.")

        time.sleep(30)

threading.Thread(target=run_scheduler, daemon=True).start()

# ==============================
# RUN BOT
# ==============================
if __name__ == "__main__":
    print("🚀 Bot berjalan...")
    bot.remove_webhook()
    time.sleep(3)

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            err_str = str(e)
            if "409" in err_str or "Conflict" in err_str:
                # Instance lama (dari deploy sebelumnya) masih zombie & belum lepas polling.
                # Tunggu lebih lama supaya tidak terus-terusan rebutan.
                print(f"⚠️ Konflik 409 terdeteksi (instance lama mungkin masih hidup). Tunggu 15 detik sebelum retry...")
                time.sleep(15)
            else:
                print(f"RESTART BOT: {e}")
                time.sleep(5)