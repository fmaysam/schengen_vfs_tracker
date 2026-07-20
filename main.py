import os
import requests
from bs4 import BeautifulSoup
import time
import schedule
import threading
import re
from flask import Flask
from urllib.parse import urljoin

# Flask initializes a tiny background website to satisfy Render's web system
app = Flask(__name__)

@app.route('/')
def home():
    return "VFS Appointment Tracker is actively operational 24/7!"

URL = "https://schengenappointments.com/in/london/tourism"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Track the actual true/false availability to completely block the 5-minute timestamp spam
last_known_status = {}

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: Missing hidden Environment Variables inside Render config.")
        return
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(telegram_url, json=payload, timeout=10)
    except Exception as e:
        print(f"Network glitch sending text to Telegram: {e}")

def get_official_vfs_link(country_page_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(country_page_url, headers=headers, timeout=10)
        if response.status_code == 200:
            sub_soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in sub_soup.find_all('a', href=True):
                href = a_tag['href']
                if "vfsglobal" in href.lower() or "vfs." in href.lower():
                    return href
            for a_tag in sub_soup.find_all('a', href=True):
                href = a_tag['href']
                if href.startswith("http") and "schengenappointments.com" not in href:
                    return href
    except Exception as e:
        print(f"Failed to extract official link from subpage: {e}")
    return country_page_url

def parse_and_clean_item(item):
    """Cleans up messy webpage elements and parses country details cleanly."""
    raw_text = " ".join(item.get_text(separator=" ").strip().split())
    if not raw_text or "pick city" in raw_text.lower() or "tourist visa" in raw_text.lower():
        return None

    # Strip away unneeded notification bells and clutter strings
    clean_text = raw_text.replace("🔔 notify me", "").replace("🔔", "").strip()
    clean_text = " ".join(clean_text.split())

    words = clean_text.split()
    if len(words) < 2:
        return None

    country_key = f"{words[0]} {words[1]}".replace(":", "").strip()
    is_available = "no availability" not in clean_text.lower()

    # Extract relative page links
    link_tag = item if item.name == 'a' else item.find('a')
    apply_link = ""
    if link_tag and link_tag.get('href'):
        apply_link = urljoin(URL, link_tag.get('href'))

    # Format the display strings beautifully based on availability
    if not is_available:
        parts = re.split(r'(?i)no availability', clean_text)
        country_name = parts[0].strip()
        time_info = parts[1].strip() if len(parts) > 1 else ""
        display_string = f"• {country_name} ({time_info})"
    else:
        display_string = f"🌍 *{clean_text}*"

    return {
        "key": country_key,
        "available": is_available,
        "link": apply_link,
        "display": display_string
    }

def check_appointments():
    global last_known_status
    print("\n--- Starting Website Scraping Cycle ---")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Bad HTTP response: {response.status_code}")
            return
            
        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.find_all('tr') or soup.find_all('div', class_='country-card') or soup.find_all('li')
        
        if not items:
            print("No layout elements detected.")
            return

        current_status = {}
        available_output = []
        unavailable_output = []
        status_changed = False

        for item in items:
            parsed = parse_and_clean_item(item)
            if not parsed:
                continue

            current_status[parsed["key"]] = parsed["available"]
            print(f"Processed -> {parsed['display']}")

            # Fetch the direct application link if slots are open
            if parsed["available"]:
                if parsed["link"]:
                    direct_vfs = get_official_vfs_link(parsed["link"])
                    parsed["display"] += f"\n👉 [Click here to Apply]({direct_vfs})"
                available_output.append(parsed["display"])
            else:
                unavailable_output.append(parsed["display"])

            # Detect genuine status changes (Available <-> Not Available)
            if last_known_status and parsed["key"] in last_known_status:
                if last_known_status[parsed["key"]] != parsed["available"]:
                    status_changed = True

        # Build the final stylized text layout
        message_content = ""
        if available_output:
            message_content += "🟢 *Available Appointments:*\n" + "\n\n".join(available_output) + "\n\n"
        if unavailable_output:
            message_content += "❌ *Not Available:*\n" + "\n".join(unavailable_output)

        # First deployment run: Send full current status report
        if not last_known_status:
            last_known_status = current_status
            startup_report = "🚀 *VFS London Monitor is Live!* Checking every 5 minutes.\n\n" + message_content
            send_telegram_message(startup_report)
            print("Initial status snapshot deployed to Telegram.")
            return

        # Subsequent runs: Only trigger if an actual slot opens or closes
        if status_changed:
            alert_report = "🔔 *VFS STATUS CHANGE DETECTED* 🔔\n\n" + message_content
            send_telegram_message(alert_report)
            print("Status change broadcast delivered to Telegram.")

        last_known_status = current_status
        print("--- Scraping Cycle Finished Successfully ---\n")
    except Exception as e:
        print(f"Error handling task cycle execution: {e}")

def run_scheduler():
    check_appointments()
    schedule.every(5).minutes.do(check_appointments)
    while True:
        schedule.run_pending()
        time.sleep(1)

# START THE TRACKER ENGINE IMMEDIATELY ON LOAD FOR GUNICORN
threading.Thread(target=run_scheduler, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
