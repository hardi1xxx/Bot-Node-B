import telebot
import gspread
import pandas as pd
import os
import json
from oauth2client.service_account import ServiceAccountCredentials

# ==============================
# CONFIG
# ==============================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN tidak ditemukan di Environment Variables!")

SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "Node B"

bot = telebot.TeleBot(TOKEN)


# ==============================
# CONNECT GOOGLE SHEET
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

        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict, scope)

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
# COMMAND START
# ==============================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Halo 👋\n\nGunakan perintah:\n/cari SITEID"
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
# RUN BOT
# ==============================

print("🚀 Bot sedang berjalan...")
bot.remove_webhook()
bot.infinity_polling(skip_pending=True)