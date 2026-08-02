import telebot
from telebot import types
import gspread
# ==============================
# MONITORING STATUS (notification code removed)
def check_status_changes():
    global last_status, first_run

    df = get_sheet_data()
    if df is None:
        print("⚠️ check_status_changes: data sheet kosong/gagal, skip cycle ini.")
        return

    state_changed = False

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

            # Maintain existing sent_history reset behavior when leaving certain statuses
            if ("L1 READY" in old_status) or ("OA CONFIRMATION" in old_status):
                stale_keys = {k for k in sent_history if k.startswith(f"{site_id}|")}
                if stale_keys:
                    sent_history.difference_update(stale_keys)
                    state_changed = True
                    print(f"   → {site_id} keluar dari status ternotifikasi, riwayat kirim di-reset ({len(stale_keys)} entri).")

            if first_run:
                continue

            # Notifications removed: do not append to changes_list or send messages.

        except Exception as e:
            print(f"ERROR LOOP: {e}")
            continue

    if state_changed:
        save_state()
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