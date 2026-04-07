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
    raise ValueError("BOT_TOKEN tidak ditemukan!")

SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "Node B"

TARGET_STATUS = [
    "-6. L0 Ready",
    "-7. L1 Ready",
    "-7. L3. OA Confirmation"
]

STATE_FILE = "last_state.json"
CHAT_FILE = "chat_ids.json"

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # WAJIB: https://domain.com/bot

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ==============================
# GOOGLE SHEET
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
# STATE
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
# CHAT STORAGE
# ==============================

def load_chats():
    if not os.path.exists(CHAT_FILE):
        return []
    with open(CHAT_FILE, "r") as f:
        return json.load(f)

def save_chats(chats):
    with open(CHAT_FILE, "w") as f:
        json.dump(chats, f)

# ==============================
# CAPTURE CHAT ID
# ==============================

@bot.message_handler(func=lambda message: True, content_types=['text'])
def capture_chat(message):
    chat_id = message.chat.id

    # Simpan hanya grup (opsional, bisa hapus kalau mau semua)
    if message.chat.type not in ["group", "supergroup"]:
        return

    chats = load_chats()
    if chat_id not in chats:
        chats.append(chat_id)
        save_chats(chats)
        print(f"Chat baru tersimpan: {chat_id}")

# ==============================
# COMMAND /start
# ==============================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Halo 👋\n\nGunakan:\n/cari SITEID\n\nBot akan kirim notifikasi otomatis ke grup ini."
    )

# ==============================
# COMMAND /cari
# ==============================

@bot.message_handler(commands=['cari'])
def search_site(message):
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        bot.reply_to(message, "Gunakan format:\n/cari SITEID")
        return

    site_id_cari = parts[1].strip()

    df = get_sheet_data()
    if df is None:
        bot.reply_to(message, "❌ Gagal mengambil data.")
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
<b>Status :</b> {row.iloc[20]}
        """

        bot.reply_to(message, response, parse_mode='HTML')

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")
        print(e)

# ==============================
# CHECK UPDATE
# ==============================

def check_updates():
    df = get_sheet_data()
    if df is None:
        print("Gagal ambil data")
        return

    last_state = load_state()
    new_state = {}

    chats = load_chats()

    for _, row in df.iterrows():
        try:
            site_id = str(row.iloc[4]).strip()
            status = str(row.iloc[20]).strip()

            new_state[site_id] = status

            if site_id in last_state:
                prev = last_state[site_id]

                if status != prev and status in TARGET_STATUS:
                    tanggal = datetime.now().strftime("%d-%m-%Y %H:%M")

                    msg = f"""
<b>🚨 UPDATE</b>
<b>Status:</b> {status}
<b>Tanggal:</b> {tanggal}

<b>Site:</b> {row.iloc[4]}-{row.iloc[7]}
<b>Witel:</b> {row.iloc[5]}
                    """

                    for chat_id in chats:
                        try:
                            bot.send_message(chat_id, msg, parse_mode="HTML")
                        except Exception as e:
                            print(f"Gagal kirim ke {chat_id}: {e}")

        except Exception as e:
            print(f"Error row: {e}")

    save_state(new_state)

# ==============================
# SCHEDULER
# ==============================

def scheduler():
    while True:
        check_updates()
        time.sleep(60)

# ==============================
# WEBHOOK
# ==============================

@app.route("/bot", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ==============================
# MAIN
# ==============================

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)

    threading.Thread(target=scheduler, daemon=True).start()

    print("🚀 Bot running...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))