import time
import random
import threading
import os
from flask import Flask
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException

# === GRUNDEINSTELLUNGEN ===
os.environ['DISPLAY'] = ':1'
WEBSITE_URL = "http://chatroom2000.de"
MAX_WAIT_TIME = 25  # Wir geben der Seite etwas mehr Zeit pro Schritt

# === FLASK APP FÜR RENDER (UNVERÄNDERT) ===
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive and running!"
def keep_alive():
    app.run(host='0.0.0.0', port=8080)

# === CHROME OPTIONS (UNVERÄNDERT) ===
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--start-maximized")
chrome_options.add_argument("--window-size=1280,800")

# === HILFSFUNKTIONEN ===
def generate_random_name():
    random_numbers = random.randint(10, 99)
    name = f"Anna 16 {random_numbers}"
    print(f"[INFO] Generierter Name: {name}")
    return name

def take_screenshot_and_upload(driver, filename_prefix):
    """Macht einen Screenshot, speichert ihn mit Zeitstempel und lädt ihn hoch."""
    try:
        filename = f"{filename_prefix}_{int(time.time())}.png"
        driver.save_screenshot(filename)
        print(f"[INFO] Screenshot '{filename}' erstellt.")
        print(f"[INFO] Lade Screenshot hoch...")
        # os.system() gibt den Befehl an das Betriebssystem weiter
        os.system(f"curl --upload-file ./{filename} https://transfer.sh/{filename}")
        print(f"[INFO] Upload-Befehl für '{filename}' ausgeführt.")
    except Exception as e:
        print(f"[ERROR] Screenshot oder Upload fehlgeschlagen: {e}")

# === LOGISCHE SCHRITTE IN FUNKTIONEN GEKAPSELT ===

def handle_cookies(driver, wait):
    """Versucht, einen der beiden bekannten Cookie-Banner zu akzeptieren."""
    print("[+] Schritt 1: Suche nach Cookie-Bannern...")
    try:
        # Versuch 1: Der "Einwilligen" Button
        cookie_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Einwilligen')]")))
        cookie_button.click()
        print("[SUCCESS] Cookie-Banner ('Einwilligen') erfolgreich weggeklickt.")
        return True
    except TimeoutException:
        print("[INFO] 'Einwilligen' Button nicht gefunden. Versuche Alternative...")
        try:
            # Versuch 2: Der "Alle akzeptieren" Button
            cookie_button_alt = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Alle akzeptieren')]")))
            cookie_button_alt.click()
            print("[SUCCESS] Cookie-Banner ('Alle akzeptieren') erfolgreich weggeklickt.")
            return True
        except TimeoutException:
            print("[WARNUNG] Keiner der bekannten Cookie-Banner wurde gefunden. Mache trotzdem weiter.")
            return True # Wir nehmen an, dass es okay ist, wenn keiner da ist.

def perform_login(driver, wait, bot_name):
    """Füllt das Login-Formular aus und klickt auf 'LOS GEHTS!'."""
    print("[+] Schritt 2: Führe Login durch...")
    try:
        print("  -> Suche Nickname-Feld...")
        nickname_field = wait.until(EC.presence_of_element_located((By.NAME, "nickname")))
        nickname_field.send_keys(bot_name)
        print(f"  -> Nickname '{bot_name}' eingegeben.")

        print("  -> Suche AGB-Checkbox...")
        agb_checkbox = wait.until(EC.element_to_be_clickable((By.ID, "tos")))
        agb_checkbox.click()
        print("  -> AGB-Checkbox angeklickt.")

        print("  -> Suche 'LOS GEHTS!'-Button...")
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='LOS GEHTS!']")))
        login_button.click()
        print("[SUCCESS] Login-Formular abgeschickt. Warte auf den Chat...")
        return True
    except (TimeoutException, NoSuchElementException, ElementNotInteractableException) as e:
        print(f"[ERROR] Kritisches Element im Login-Formular nicht gefunden oder nicht klickbar: {e}")
        return False

def dismiss_popups(driver, wait):
    """Klickt alle drei bekannten Pop-ups nach dem Login weg."""
    print("[+] Schritt 3: Klicke nachfolgende Pop-ups weg...")
    popups = ["Chatregeln", "Unsere Do's", "Probleme-Fenster"]
    for i, popup_name in enumerate(popups):
        try:
            print(f"  -> Warte auf Pop-up: '{popup_name}'...")
            # Die meisten Buttons enthalten 'Akzeptieren' oder 'Fertig'
            button_xpath = "//button[contains(., 'Akzeptieren') or contains(., 'Fertig')]"
            popup_button = wait.until(EC.element_to_be_clickable((By.XPATH, button_xpath)))
            popup_button.click()
            print(f"  -> '{popup_name}' erfolgreich weggeklickt.")
            time.sleep(2)  # Kurze Pause, damit das nächste Pop-up erscheinen kann
        except TimeoutException:
            print(f"[WARNUNG] Pop-up '{popup_name}' ist nicht erschienen. Ignoriere und mache weiter.")
            # Das ist kein kritischer Fehler, also geben wir True zurück
    print("[SUCCESS] Alle erwarteten Pop-ups behandelt. Bot ist im Chatraum.")
    return True

def message_loop(driver, wait, bot_name):
    """Hauptschleife, die Nachrichten sendet."""
    print("[+] Schritt 4: Starte Nachrichtenschleife...")
    while True:
        try:
            message_to_send = f"Hallo! Ich bin's, {bot_name}. Es ist {time.strftime('%H:%M:%S')}."
            
            print("  -> Suche Nachrichten-Eingabefeld...")
            message_field = wait.until(EC.presence_of_element_located((By.NAME, "message")))
            
            print(f"  -> Sende Nachricht: '{message_to_send}'")
            message_field.send_keys(message_to_send)
            message_field.send_keys(Keys.RETURN)
            
            print(f"[SUCCESS] Nachricht gesendet. Warte 60 Sekunden...")
            time.sleep(60)
        except Exception as loop_error:
            print(f"[ERROR] Fehler in der Nachrichtenschleife: {loop_error}")
            # Bricht die innere Schleife ab, löst aber den Neustart des Bots aus.
            return

# === HAUPTFUNKTION, DIE ALLES STEUERT ===
def start_bot():
    print("\n" + "="*50)
    print(f"Starte neuen Bot-Zyklus am {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    driver = None
    try:
        print("[INFO] Versuche, den Chrome WebDriver zu starten...")
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, MAX_WAIT_TIME)
        print("[SUCCESS] WebDriver erfolgreich gestartet.")
        
        print(f"[INFO] Lade Webseite: {WEBSITE_URL}...")
        driver.get(WEBSITE_URL)
        print("[SUCCESS] Webseite geladen.")

        # Führe die Schritte nacheinander aus. Wenn einer fehlschlägt, bricht die Kette ab.
        if not handle_cookies(driver, wait):
            raise Exception("Fehler bei der Cookie-Behandlung.")
        
        bot_name = generate_random_name()
        if not perform_login(driver, wait, bot_name):
            raise Exception("Fehler beim Login-Vorgang.")
        
        if not dismiss_popups(driver, wait):
            raise Exception("Fehler beim Wegklicken der Pop-ups.")
            
        # Wenn wir hier ankommen, war der Login erfolgreich. Machen wir einen Beweis-Screenshot.
        take_screenshot_and_upload(driver, "login_success")
        
        # Starte die Endlos-Schleife für Nachrichten
        message_loop(driver, wait, bot_name)

    except Exception as e:
        print("!"*50)
        print(f"[FATAL] Ein schwerwiegender, unerwarteter Fehler ist im Hauptprozess aufgetreten: {e}")
        print("!"*50)
        if driver:
            take_screenshot_and_upload(driver, "fatal_error")
    
    finally:
        if driver:
            print("[INFO] Schließe den Browser und räume auf...")
            driver.quit()
        print("[INFO] Bot-Zyklus beendet. Neustart wird vorbereitet.")

# === STARTPUNKT DES PROGRAMMS ===
if __name__ == "__main__":
    print("[MAIN] Starte den Keep-alive Server in einem Hintergrund-Thread...")
    t = threading.Thread(target=keep_alive)
    t.daemon = True
    t.start()
    
    print("[MAIN] Starte die Haupt-Bot-Schleife...")
    while True:
        start_bot()
        print(f"[MAIN] Nächster Bot-Start in 15 Sekunden...")
        time.sleep(15)
