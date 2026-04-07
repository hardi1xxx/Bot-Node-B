import telebot
import gspread
import pandas as pd
import os
import json
import threading
import time
from datetime import datetime
from flask import Flask, request
from oauth2client.service_account import ServiceAccountCredentials

# ==============================
# CONFIG
# ==============================

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN tidak ditemukan di Environment Variables!")

SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "Node B"

TARGET_STATUS = [
    "-6. L0 Ready",
    "-7. L1 Ready",
    "-7. L3. OA Confirmation"
]

STATE_FILE = "last_state.json"

# Ganti dengan chat ID grup Telegram
GROUP_CHAT_ID = "ISI_GROUP_CHAT_ID"

# Untuk webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # contoh: https://myapp.up.railway.app/bot

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ==============================
# GOOGLE SHEET CONNECT
# ==============================

def get_sheet_data():
    try:
        credentials_raw = os.getenv("GOOGLE_CREDENTIALS")
        if not credentials_raw:
            raise ValueError("GOOGLE_CREDENTIALS tidak ditemukan!")

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_dict = json.loads(credentials_raw)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(NAMA_SHEET)
        data = sheet.get_all_values()

        if not data:
            return None

        df = pd.DataFrame(data)
        headers = df.iloc[0]
        df = df[1:]
        df.columns = headers

        return df
    except Exception as e:
        print(f"ERROR GOOGLE SHEET: {e}")
        return None

# ==============================
# STATE HANDLER
# ==============================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ==============================
# COMMAND /start
# ==============================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Halo 👋\n\nGunakan perintah:\n/cari SITEID\n\nBot otomatis memberi notifikasi di grup jika ada update status tertentu."
    )

# ==============================
# COMMAND /cari
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
        bot.reply_to(message, "❌ Gagal mengambil data dari Google Sheet.")
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
        bot.reply_to(message, f"❌ Terjadi error: {str(e)}")
        print(f"DETAIL ERROR: {e}")

# ==============================
# CEK PERUBAHAN DATA (NOTIFIKASI)
# ==============================

def check_updates():
    print("🔍 Cek update Google Sheet...")
    df = get_sheet_data()
    if df is None:
        print("❌ Gagal ambil data")
        return

    last_state = load_state()
    new_state = {}

    for i, row in df.iterrows():
        try:
            site_id = str(row.iloc[4]).strip()
            status = str(row.iloc[20]).strip()
            new_state[site_id] = status

            # Cek: hanya kirim jika status berubah dan termasuk TARGET_STATUS
            if site_id in last_state:
                prev_status = last_state[site_id]
                if status != prev_status and status in TARGET_STATUS:
                    tanggal = datetime.now().strftime("%d-%m-%Y %H:%M")
                    response = f"""
<b>🚨 UPDATE DATA BARU</b>
━━━━━━━━━━━━━━━
<b>Status Baru :</b> {status}
<b>Tanggal :</b> {tanggal}
━━━━━━━━━━━━━━━
<b>📋 DATA SITE</b>
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
                    try:
                        bot.send_message(GROUP_CHAT_ID, response, parse_mode="HTML")
                        print(f"Notifikasi terkirim: {site_id} → {status}")
                    except Exception as e:
                        print(f"Gagal kirim notifikasi ke grup: {e}")
            else:
                # Kalau site_id baru, simpan state tapi tidak kirim notif
                pass

        except Exception as e:
            print(f"Error row: {e}")

    save_state(new_state)
    save_state(new_state)

# ==============================
# SCHEDULER LOOP (cek tiap 60 detik)
# ==============================

def scheduler():
    while True:
        check_updates()
        time.sleep(60)

threading.Thread(target=scheduler).start()

# ==============================
# WEBHOOK SETUP
# ==============================

@app.route(f"/bot", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

# ==============================
# RUN FLASK
# ==============================

if __name__ == "__main__":
    # hapus webhook lama dulu
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print("🚀 Bot siap menerima webhook...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))