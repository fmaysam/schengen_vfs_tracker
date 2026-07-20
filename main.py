import os
import requests
from bs4 import BeautifulSoup
import time
import schedule
import threading
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

last_known_data = {}

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
    """Visits the second page to find the direct official VFS application link."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(country_page_url, headers=headers, timeout=10)
        if response.status_code == 200:
            sub_soup = BeautifulSoup(response.text, 'html.parser')
            # Look for links that point to VFS Global or external official sites
            for a_tag in sub_soup.find_all('a', href=True):
                href = a_tag['href']
                if "vfsglobal" in href.lower() or "vfs." in href.lower():
                    return href
            
            # Fallback: Look for any external link that doesn't belong to schengenappointments
            for a_tag in sub_soup.find_all('a', href=True):
                href = a_tag['href']
                if href.startswith("http") and "schengenappointments.com" not in href:
                    return href
    except Exception as e:
        print(f"Failed to extract official link from subpage {country_page_url}: {e}")
    
    # Ultimate fallback: return the subpage link itself if direct link is not found
    return country_page_url

def check_appointments():
    global last_known_data
    print("\n--- Starting Website Scraping Cycle ---")
    print(f"Targeting URL: {URL}")
    
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
        items = soup.find_all('tr') or soup.find_all('div', class_='country-card') or soup.find_all('li')
        
        if not items:
            print("Layout parsed but found empty data cards.")
            return

        current_data = {}
        changes_detected = []
        available_now = []

        for item in items:
            text_content = " ".join(item.get_text(separator=" ").strip().split())
            if not text_content or "pick city" in text_content.lower() or "tourist visa" in text_content.lower():
                continue
            
            words = text_content.split()
            if len(words) < 2:
                continue
                
            # Create a clean country key name
            country_key = f"{words[0]} {words[1]}".replace(":", "").strip()
            current_data[country_key] = text_content
            
            # Print to Render logs so you can see the live action
            print(f"Found Data -> {text_content}")

            # Find the link tag associated with this country
            link_tag = item if item.name == 'a' else item.find('a')
            apply_link = ""
            if link_tag and link_tag.get('href'):
                relative_href = link_tag.get('href')
                sub_page_url = urljoin(URL, relative_href)
                
                # If this country has open slots, grab the official booking link from page 2
                if "no availability" not in text_content.lower():
                    print(f"Slots found for {country_key}! Fetching official link...")
                    apply_link = get_official_vfs_link(sub_page_url)

            # Build notification layout strings
            if "no availability" not in text_content.lower():
                link_markdown = f" \n👉 [Click here to Apply]({apply_link})" if apply_link else ""
                available_now.append(f"🌍 *{text_content}*{link_markdown}")
            
            # Track changes on subsequent runs
            if last_known_data and country_key in last_known_data:
                if last_known_data[country_key] != text_content:
                    link_markdown = f" \n👉 [Click here to Apply]({apply_link})" if apply_link else ""
                    changes_detected.append(f"⚠️ *STATUS CHANGE FOR {country_key.upper()}*:\n`{text_content}`{link_markdown}")

        # First connection initialization
        if not last_known_data:
            last_known_data = current_data
            startup_msg = "🚀 *VFS London Monitor is Live!* Checking every 5 minutes.\n\n"
            if available_now:
                startup_msg += "📊 *Current Available Slots Right Now:*\n\n" + "\n\n".join(available_now)
            else:
                startup_msg += "❌ No appointments available anywhere on the list right now."
            
            send_telegram_message(startup_msg)
            print("Startup report sent to Telegram.")
            return

        # Broadcast message if data changes on later runs
        if changes_detected:
            alert_msg = "🔔 *VFS UPDATE DETECTED* 🔔\n\n" + "\n\n".join(changes_detected)
            send_telegram_message(alert_msg)
            print("Update alert sent to Telegram.")

        last_known_data = current_data
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
