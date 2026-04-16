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

CACHE_DURATION = 30  # detik

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
            raise ValueError("GOOGLE_CREDENTIALS tidak ditemukan!")

        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_dict = json.loads(credentials_raw)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)

        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(NAMA_SHEET)

        data = sheet.get_all_values()

        if not data:
            return None

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

    bot.reply_to(
        message,
        "Halo 👋\n\nGunakan:\n/cari SITEID"
    )

# ==============================
# COMMAND CARI
# ==============================
@bot.message_handler(commands=['cari'])
def search_site(message):
    try:
        site_id_cari = message.text.split(maxsplit=1)[1].strip()
    except:
        bot.reply_to(message, "Gunakan format:\n/cari SITEID")
        return

    df = get_sheet_data()

    if df is None:
        bot.reply_to(message, "❌ Gagal ambil data.")
        return

    try:
        result = df[df.iloc[:, 4].astype(str).str.strip().str.upper() == site_id_cari.upper()]

        if result.empty:
            bot.reply_to(message, f"❌ Site ID '{site_id_cari}' tidak ditemukan.")
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

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ==============================
# KIRIM NOTIF (FORMAT SESUAI REQUEST)
# ==============================
def send_notif(row):
    message = f"""
<b>🚨 NOTIFIKASI STATUS BERUBAH</b>
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

    changes = 0

    for _, row in df.iterrows():
        try:
            site_id = str(row.iloc[4]).strip()
            status = str(row.iloc[20]).strip().upper()

            # pertama kali (initial load)
            if site_id not in last_status:
                last_status[site_id] = status

                if not first_run and any(x in status for x in ["L1 READY", "OA CONFIRMATION"]):
                    send_notif(row)

                continue

            # tidak berubah
            if last_status[site_id] == status:
                continue

            # berubah
            last_status[site_id] = status
            changes += 1

            if any(x in status for x in ["7. L1 Ready", "7. L3. OA Confirmation"]):
                send_notif(row)

        except Exception as e:
            print(f"ERROR LOOP: {e}")
            continue

    if changes > 0:
        print(f"✅ Perubahan: {changes}")

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
    bot.infinity_polling(skip_pending=True)