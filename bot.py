import telebot
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

SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "Node B"

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

# ==============================
# COMMAND START
# ==============================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_chats.add(message.chat.id)

    bot.reply_to(message, "✅ Bot aktif!\nGunakan:\n/cari SITEID")

# ==============================
# COMMAND CARI
# ==============================
@bot.message_handler(commands=['cari'])
def search_site(message):
    try:
        site_id_cari = message.text.split(maxsplit=1)[1].strip()
    except:
        bot.reply_to(message, "Gunakan:\n/cari SITEID")
        return

    df = get_sheet_data()

    if df is None:
        bot.reply_to(message, "❌ Gagal ambil data.")
        return

    result = df[df.iloc[:, 4].astype(str).str.strip().str.upper() == site_id_cari.upper()]

    if result.empty:
        bot.reply_to(message, "❌ Tidak ditemukan")
        return

    row = result.iloc[0]

    response = f"""
<b>📋 DATA SITE</b>
━━━━━━━━━━━━━━━

<b>Site ID :</b> {row.iloc[4]}-{row.iloc[7]}
<b>Plan Deploy :</b> {row.iloc[1]}
<b>Sub Sistem :</b> {row.iloc[3]}
<b>Witel & STO :</b> {row.iloc[5]} ({row.iloc[6]})
<b>Status Pekerjaan :</b> {row.iloc[20]}
<b>Catuan :</b> {row.iloc[28]}
<b>Panjang Kabel :</b> {row.iloc[29]}
<b>Jenis Kabel :</b> {row.iloc[30]} ({row.iloc[31]})
<b>Tiang :</b> {row.iloc[32]}
<b>Nilai BoQ (Survey) :</b> {row.iloc[33]}
<b>New TA AREA :</b> {row.iloc[66]}
<b>NEW INFRA / FIBERIZATION :</b> {row.iloc[100]}
    """

    bot.reply_to(message, response, parse_mode='HTML')

# ==============================
# DASHBOARD NOTIF
# ==============================
def send_dashboard(changes_list):
    if not changes_list:
        return

    message = "<b>🚨 UPDATE STATUS (DASHBOARD)</b>\n━━━━━━━━━━━━━━━\n\n"

    for row in changes_list:
        message += f"""
<b>{row.iloc[4]}-{row.iloc[7]}</b>
Status : {row.iloc[20]}
Witel  : {row.iloc[5]}

"""

    message += f"\nTotal Update: {len(changes_list)}"

    for chat_id in user_chats:
        try:
            bot.send_message(chat_id, message, parse_mode='HTML')
        except:
            pass

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
            status = clean_status(row.iloc[20])

            if site_id not in last_status:
                last_status[site_id] = status
                continue

            if last_status[site_id] == status:
                continue

            old_status = last_status[site_id]
            last_status[site_id] = status

            print(f"{site_id} | {old_status} -> {status}")

            if first_run:
                continue

            key = f"{site_id}-{status}"

            if ("L1 READY" in status) or ("OA CONFIRMATION" in status):
                
                # kalau sudah pernah dikirim → skip
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