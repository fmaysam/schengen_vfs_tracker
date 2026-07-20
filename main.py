import os
import requests
from bs4 import BeautifulSoup
import time
import schedule
import threading
from flask import Flask

# Flask initializes a tiny background website to satisfy Render's web system
app = Flask(__name__)

@app.route('/')
def home():
    return "VFS Appointment Tracker is actively operational 24/7!"

URL = "https://schengenappointments.com/in/london/tourism"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

last_known_data = {}

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: Missing hidden Environment Variables inside Render config.")
        return
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(telegram_url, json=payload, timeout=10)
    except Exception as e:
        print(f"Network glitch sending text to Telegram: {e}")

def check_appointments():
    global last_known_data
    print("Scraping target tracker website...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Server responded with bad HTTP code: {response.status_code}")
            return
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Pulls structural table rows or grid div modules
        items = soup.find_all('tr') or soup.find_all('div', class_='country-card')
        
        if not items:
            print("Layout parsed layout but found empty data cards.")
            return

        current_data = {}
        changes_detected = []

        for item in items:
            text_content = " ".join(item.get_text(separator=" ").strip().split())
            if not text_content:
                continue
            
            words = text_content.split()
            if len(words) < 2:
                continue
                
            # Identifies unique rows by country prefixes safely
            country_key = f"{words[0]} {words[1]}"
            current_data[country_key] = text_content
            
            if country_key in last_known_data:
                if last_known_data[country_key] != text_content:
                    changes_detected.append(f"⚠️ *UPDATE FOR {country_key.upper()}*:\n`{text_content}`")

        # First connection initialization acknowledgement
        if not last_known_data:
            last_known_data = current_data
            send_telegram_message("🚀 *VFS London Monitor is live from the Cloud!* Checking every 5 minutes.")
            return

        # Broadcast text message block if data morphs
        if changes_detected:
            alert_msg = "🔔 *NEW VFS LONDON APPOINTMENT INFO FOUND* 🔔\n\n" + "\n\n".join(changes_detected)
            send_telegram_message(alert_msg)

        last_known_data = current_data
    except Exception as e:
        print(f"Error handling task cycle execution: {e}")

def run_scheduler():
    # Initial trigger check right at system startup
    check_appointments()
    schedule.every(5).minutes.do(check_appointments)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # Spins up tracking logic context inside a secondary engine thread
    threading.Thread(target=run_scheduler, daemon=True).start()
    # Runs the frontend app server allocation setup
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
