import os
import time
import subprocess
import threading
import socket
import requests
import matplotlib.pyplot as plt
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = '7971605755:AAHAh9QO9BVS9dLAWYB4ZZ1XxCGZ-15Ut2M'

user_data = {}
mining_jobs = {}
jobs_lock = threading.Lock()
auto_restart_enabled = {}
last_paid_amount = {}

# Utils
def get_repo_name():
    return os.path.basename(os.getcwd())

def get_username():
    return os.getenv("CODESPACE_NAME", socket.gethostname())

def get_machine_info():
    try:
        return subprocess.check_output(['uname', '-a']).decode().strip()
    except:
        return "unknown"

def get_pool_stats(wallet):
    try:
        r = requests.get(f"https://moneroocean.stream/api/user/stats?address={wallet}", timeout=5)
        return r.json() if r.status_code == 200 else None
    except:
        return None

# Start miner
def start_mining_process(wallet):
    cmd = ['./xmrig', '-o', 'gulf.moneroocean.stream:10128', '-u', wallet, '-p', 'code', '-a', 'randomx', '--donate-level=1', '--threads=1']
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def start_mining(user_id, wallet):
    with jobs_lock:
        if user_id in mining_jobs:
            for job in mining_jobs[user_id]:
                try: job['proc'].terminate()
                except: pass
        mining_jobs[user_id] = []
        for _ in range(4):
            proc = start_mining_process(wallet)
            mining_jobs[user_id].append({'proc': proc, 'start_time': time.time(), 'hashes': 0})

        def simulate_hashes():
            while True:
                time.sleep(1)
                with jobs_lock:
                    if user_id not in mining_jobs: break
                    for job in mining_jobs[user_id]:
                        if job['proc'].poll() is not None:
                            mining_jobs[user_id].remove(job)
                            continue
                        job['hashes'] += 1000
        threading.Thread(target=simulate_hashes, daemon=True).start()

# Auto-restart crash protection
def auto_restart_loop():
    while True:
        time.sleep(10)
        with jobs_lock:
            for user_id in list(mining_jobs.keys()):
                if auto_restart_enabled.get(user_id):
                    for i, job in enumerate(mining_jobs[user_id]):
                        if job['proc'].poll() is not None:
                            print(f"[AutoRestart] Restarting thread for user {user_id}")
                            new_proc = start_mining_process(user_data[user_id]['wallet'])
                            mining_jobs[user_id][i] = {'proc': new_proc, 'start_time': time.time(), 'hashes': 0}

threading.Thread(target=auto_restart_loop, daemon=True).start()

# Payment notifier
def payment_notifier_loop(app):
    while True:
        time.sleep(60)
        for user_id, info in user_data.items():
            stats = get_pool_stats(info['wallet'])
            if stats:
                paid = stats.get("amtPaid", 0) / 1e12
                if user_id not in last_paid_amount:
                    last_paid_amount[user_id] = paid
                elif paid > last_paid_amount[user_id]:
                    amount = paid - last_paid_amount[user_id]
                    last_paid_amount[user_id] = paid
                    try:
                        app.bot.send_message(chat_id=user_id, text=f"💸 *Payment Received:* {amount:.6f} XMR", parse_mode='Markdown')
                    except Exception as e:
                        print(f"[PaymentAlertError] {e}")

# Commands
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Use: /wallet <your_xmr_wallet>")
        return
    wallet_addr = context.args[0]
    user_data[user_id] = {
        'wallet': wallet_addr,
        'start_time': time.time(),
        'hashes': 0,
        'repo': get_repo_name(),
        'user': get_username(),
        'system': get_machine_info()
    }
    await update.message.reply_text(f"💼 Wallet saved: `{wallet_addr}`", parse_mode='Markdown')

async def start_mine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("⚠️ Set wallet first using /wallet")
        return
    await start_mining(user_id, user_data[user_id]['wallet'])
    await update.message.reply_text("🚀 Brutal mining started with 4 threads!")

async def restart_on_crash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    auto_restart_enabled[user_id] = True
    await update.message.reply_text("🔁 Auto-restart on crash is now *enabled*", parse_mode='Markdown')

async def uptime_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in mining_jobs or not mining_jobs[user_id]:
        await update.message.reply_text("⚠️ Mining not running.")
        return
    uptimes = [int(time.time() - job['start_time']) for job in mining_jobs[user_id]]
    plt.figure()
    plt.bar(range(1, len(uptimes)+1), uptimes)
    plt.title("Thread Uptime (Seconds)")
    plt.xlabel("Thread")
    plt.ylabel("Uptime")
    plt.savefig("uptime.png")
    plt.close()
    with open("uptime.png", "rb") as f:
        await update.message.reply_photo(InputFile(f), caption="📊 *Uptime per Thread*", parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("❌ No wallet set.")
        return
    with jobs_lock:
        if user_id not in mining_jobs or not mining_jobs[user_id]:
            await update.message.reply_text("⚠️ Mining not running. Use /start_mine")
            return
        total_hashes = sum(job['hashes'] for job in mining_jobs[user_id])
        total_uptime = sum(time.time() - job['start_time'] for job in mining_jobs[user_id])
        running_jobs = sum(1 for job in mining_jobs[user_id] if job['proc'].poll() is None)
        hashrate = int(total_hashes / total_uptime) if total_uptime > 0 else 0
        stats = get_pool_stats(user_data[user_id]['wallet'])
        if stats:
            paid = stats.get("amtPaid", 0) / 1e12
            unpaid = stats.get("amtDue", 0) / 1e12
            total = paid + unpaid
        else:
            paid = unpaid = total = 0
        msg = (
            f"🛠️ *Mining Dashboard*\n\n"
            f"👤 *User:* `{user_data[user_id]['user']}`\n"
            f"📦 *Repo:* `{user_data[user_id]['repo']}`\n"
            f"💰 *Wallet:* `{user_data[user_id]['wallet']}`\n"
            f"🖥️ *Machine:* `{user_data[user_id]['system']}`\n\n"
            f"⚙️ *Jobs:* {running_jobs}/4\n"
            f"⏱️ *Uptime:* {int(total_uptime)}s\n"
            f"💥 *Hashes:* {total_hashes}\n"
            f"⚡ *Hashrate:* {hashrate} H/s\n\n"
            f"💸 *Paid:* {paid:.6f} XMR\n"
            f"🧾 *Unpaid:* {unpaid:.6f} XMR\n"
            f"📊 *Total Earned:* {total:.6f} XMR"
        )
        await update.message.reply_markdown(msg)

async def graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("❌ Set wallet first.")
        return
    stats = get_pool_stats(user_data[user_id]['wallet'])
    if not stats or "hashrate" not in stats:
        await update.message.reply_text("⚠️ Couldn't fetch hashrate stats.")
        return
    hashrate_data = stats["hashrate"]
    timestamps = [i["ts"] for i in hashrate_data][-20:]
    values = [i["h"] for i in hashrate_data][-20:]
    plt.figure()
    plt.plot(timestamps, values, marker='o')
    plt.title("Live Hashrate")
    plt.xlabel("Time")
    plt.ylabel("Hashrate (H/s)")
    plt.grid(True)
    plt.savefig("hashrate.png")
    plt.close()
    with open("hashrate.png", "rb") as f:
        await update.message.reply_photo(InputFile(f), caption="📈 *Live Hashrate*", parse_mode='Markdown')

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    with jobs_lock:
        if user_id not in mining_jobs or not mining_jobs[user_id]:
            await update.message.reply_text("⚠️ No mining active.")
            return
        for job in mining_jobs[user_id]:
            try: job['proc'].terminate()
            except: pass
        mining_jobs[user_id] = []
    await update.message.reply_text("🛑 Brutal mining stopped.")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👑 *Brutal XMR Bot Ready!*\n"
        "Use /wallet <XMR_wallet> to set wallet\n"
        "Then /start_mine to begin mining.\n"
        "Use /help for all commands.",
        parse_mode='Markdown'
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 *Commands List:*\n"
        "/wallet <XMR_wallet>\n"
        "/start_mine\n"
        "/status\n"
        "/graph\n"
        "/uptime_chart\n"
        "/restart_on_crash\n"
        "/stop\n"
        "/help",
        parse_mode='Markdown'
    )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("start_mine", start_mine))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("graph", graph))
    app.add_handler(CommandHandler("uptime_chart", uptime_chart))
    app.add_handler(CommandHandler("restart_on_crash", restart_on_crash))
    app.add_handler(CommandHandler("stop", stop))
    threading.Thread(target=payment_notifier_loop, args=(app,), daemon=True).start()
    print("🔥 Brutal XMR Mining Bot Running")
    app.run_polling()

if __name__ == "__main__":
    main()
