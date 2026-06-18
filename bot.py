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
# GLOBAL VARIABLE
# ==============================
user_chats = set()
last_status = {}
last_fetch_time = 0
cached_df = None
first_run = True
sent_history = set()
CACHE_DURATION = 30

# ==============================
# CONFIG
# ==============================
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN tidak ditemukan!")

SPREADSHEET_ID = "1h1NBs7k4rCibwFvNVu9t0rIlq-TuF7sh6YZvxhu9VqQ"
NAMA_SHEET = "All Node B"

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://bot-node-b-web-bghh-production.up.railway.app")

bot = telebot.TeleBot(TOKEN)

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
        credentials_raw = os.getenv("GOOGLE_CREDENTIALS")
        if not credentials_raw:
            raise ValueError("GOOGLE_CREDENTIALS environment variable tidak ditemukan!")

        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_dict = json.loads(credentials_raw)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)

        # Gunakan authorize (kompatibel semua versi gspread)
        client = gspread.authorize(creds)

        spreadsheet = client.open_by_key(SPREADSHEET_ID)

        # FIX: Cari sheet dengan nama yang cocok (case-insensitive + strip spasi)
        sheet = None
        for ws in spreadsheet.worksheets():
            ws_title = ws.title.strip()
            print(f"  → Sheet ditemukan: '{ws_title}'")
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
        print(f"✅ Data berhasil diambil: {len(df)} baris, {len(df.columns)} kolom")

        return df

    except Exception as e:
        print(f"ERROR GOOGLE SHEET: {e}")
        return None

# ==============================
# COMMAND START
# ==============================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_chats.add(message.chat.id)

    markup = types.InlineKeyboardMarkup()
    if message.chat.type == "private":
        # Di chat pribadi: buka sebagai Web App (langsung di dalam Telegram)
        markup.add(types.InlineKeyboardButton(
            "📡 Buka Dashboard",
            web_app=types.WebAppInfo(url=WEBAPP_URL)
        ))
    else:
        # Di grup: Telegram tidak izinkan web_app inline button,
        # jadi pakai link biasa (terbuka di browser)
        markup.add(types.InlineKeyboardButton(
            "📡 Buka Dashboard",
            url=WEBAPP_URL
        ))

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

    # Cari berdasarkan kolom SITE ID (index 4)
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

    site_id_full = f"{safe(4)}-{safe(7)}"
    markup = types.InlineKeyboardMarkup()
    if message.chat.type == "private":
        markup.add(types.InlineKeyboardButton(
            f"📡 Lihat di Dashboard",
            web_app=types.WebAppInfo(url=WEBAPP_URL)
        ))
    else:
        markup.add(types.InlineKeyboardButton(
            f"📡 Lihat di Dashboard",
            url=WEBAPP_URL
        ))

    bot.reply_to(message, response, parse_mode='HTML', reply_markup=markup)

# ==============================
# DASHBOARD NOTIF
# ==============================
def send_dashboard(changes_list):
    if not changes_list:
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

    for chat_id in list(user_chats):
        try:
            chat = bot.get_chat(chat_id)
            markup = types.InlineKeyboardMarkup()
            if chat.type == "private":
                markup.add(types.InlineKeyboardButton(
                    "📡 Buka Dashboard",
                    web_app=types.WebAppInfo(url=WEBAPP_URL)
                ))
            else:
                markup.add(types.InlineKeyboardButton(
                    "📡 Buka Dashboard",
                    url=WEBAPP_URL
                ))
            bot.send_message(chat_id, message, parse_mode='HTML', reply_markup=markup)
        except Exception as e:
            print(f"Gagal kirim ke {chat_id}: {e}")

# ==============================
# MONITORING STATUS
# ==============================
def check_status_changes():
    global last_status, first_run

    df = get_sheet_data()
    if df is None:
        return

    changes_list = []

    for _, row in df.iterrows():
        try:
            site_id = str(row.iloc[4]).strip()
            if not site_id or site_id == "nan":
                continue

            status = clean_status(row.iloc[20])

            if site_id not in last_status:
                last_status[site_id] = status
                continue

            if last_status[site_id] == status:
                continue

            old_status = last_status[site_id]
            last_status[site_id] = status

            print(f"[STATUS] {site_id} | {old_status} → {status}")

            if first_run:
                continue

            key = f"{site_id}-{status}"

            if ("L1 READY" in status) or ("OA CONFIRMATION" in status):
                if key in sent_history:
                    continue
                changes_list.append(row)
                sent_history.add(key)

        except Exception as e:
            print(f"ERROR LOOP: {e}")
            continue

    if changes_list:
        send_dashboard(changes_list)
        print(f"✅ Notif dashboard: {len(changes_list)}")

# ==============================
# SCHEDULER
# ==============================
def run_scheduler():
    global first_run

    while True:
        check_status_changes()

        if first_run:
            first_run = False
            print("✅ First run selesai. Monitoring aktif.")

        time.sleep(30)

threading.Thread(target=run_scheduler, daemon=True).start()

# ==============================
# RUN BOT
# ==============================
if __name__ == "__main__":
    print("🚀 Bot berjalan...")
    bot.remove_webhook()
    time.sleep(2)

    while True:
        try:
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            print(f"RESTART BOT: {e}")
            time.sleep(5)