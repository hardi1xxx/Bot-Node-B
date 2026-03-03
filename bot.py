import telebot
import gspread
import pandas as pd

# --- KONFIGURASI BARU ---
TOKEN = "8752926914:AAF7_o9c-fvl2HZ0FOoVolxGr3sggKH3Iog"
SPREADSHEET_ID = "124EjHM5jfcsLez2G0R2_ZSpD9He-IjawllH1N8BJXng"
NAMA_SHEET = "Node B"  # Nama Sheet yang baru

# Inisialisasi Bot
bot = telebot.TeleBot(TOKEN)

# Fungsi untuk koneksi ke Google Sheet (Tanpa Credentials karena Public)
def get_sheet_data():
    try:
        # Pakai Service Account
        client = gspread.service_account(filename="service_account.json")
        
        # Buka spreadsheet
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
    bot.reply_to(message, 
        "Halo! Saya Bot Info Site.\n\n" +
        "Silakan masukkan Site ID yang ingin dicari."
    )

@bot.message_handler(func=lambda message: True)
def echo_message(message):
    site_id_cari = message.text.strip()
    
    df = get_sheet_data()
    
    if df is None:
        bot.reply_to(message, "❌ Gagal mengambil data dari Google Sheet.\n\nCoba cek:\n1. Apakah sheet 'Node B' benar?\n2. Apakah link sudah di Public?")
        return
    
    try:
        # Cari berdasarkan Site ID (Kolom E / Index 4)
        result = df[df.iloc[:, 4].astype(str).str.strip() == site_id_cari]
        
        if result.empty:
            result = df[df.iloc[:, 4].astype(str).str.upper().str.strip() == site_id_cari.upper()]
        
        if result.empty:
            bot.reply_to(message, f"❌ Site ID '{site_id_cari}' tidak ditemukan.\n\nCoba cek lagi Site ID-nya.")
        else:
            row = result.iloc[0]
            
            #CEK: Kita coba dulu index kolom yang benar
            #Coba print(row) untuk debug
            print(f"Data ditemukan: {row.iloc[4]}")
            print(f"Jumlah kolom: {len(row)}")
            
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
bot.infinity_polling()