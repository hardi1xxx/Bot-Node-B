import telebot
import gspread
import pandas as pd
import os
import json
from oauth2client.service_account import ServiceAccountCredentials

# --- KONFIGURASI ---
TOKEN = os.getenv("8752926914:AAF7_o9c-fvl2HZ0FOoVolxGr3sggKH3Iog")
SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "Node B"

# Inisialisasi Bot
bot = telebot.TeleBot(TOKEN)

# Fungsi koneksi ke Google Sheet (pakai ENV Railway)
def get_sheet_data():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

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
        print(f"Error: {e}")
        return None


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Halo! Saya Bot Info Site.\n\nSilakan masukkan Site ID yang ingin dicari."
    )


@bot.message_handler(func=lambda message: True)
def echo_message(message):
    site_id_cari = message.text.strip()

    df = get_sheet_data()

    if df is None:
        bot.reply_to(
            message,
            "❌ Gagal mengambil data dari Google Sheet.\n\nCek ENV GOOGLE_CREDENTIALS di Railway."
        )
        return

    try:
        result = df[df.iloc[:, 4].astype(str).str.strip() == site_id_cari]

        if result.empty:
            result = df[df.iloc[:, 4].astype(str).str.upper().str.strip() == site_id_cari.upper()]

        if result.empty:
            bot.reply_to(
                message,
                f"❌ Site ID '{site_id_cari}' tidak ditemukan."
            )
        else:
            row = result.iloc[0]

            response = f"""
<b>📋 DATA SITE</b>
━━━━━━━━━━━━━━━

<b>Site ID :</b> {row.iloc[4]}
<b>Plan Deploy :</b> {row.iloc[1]}
<b>Sub Sistem :</b> {row.iloc[3]}
<b>Witel & STO :</b> {row.iloc[5]} ({row.iloc[6]})
<b>Status Pekerjaan :</b> {row.iloc[20]}
<b>Catuan :</b> {row.iloc[28]}
<b>Panjang Kabel :</b> {row.iloc[29]}
<b>Jenis Kabel :</b> {row.iloc[30]} ({row.iloc[31]})
<b>Tiang :</b> {row.iloc[32]}
<b>Nilai BoQ (Survey) :</b> {row.iloc[35]}
<b>New TA AREA :</b> {row.iloc[66]}
<b>NEW INFRA / FIBERIZATION :</b> {row.iloc[100]}
            """

            bot.reply_to(message, response, parse_mode='HTML')

    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")
        print(f"Error Detail: {e}")


print("Bot sedang berjalan...")
bot.remove_webhook()
bot.infinity_polling()