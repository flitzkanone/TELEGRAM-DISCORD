import os
import logging
import json
import random
from dotenv import load_dotenv
from datetime import datetime, timedelta
from io import BytesIO
import asyncio
import re
from math import ceil

# NEU: Discord-Bibliothek importieren
from discord_webhook import DiscordWebhook, DiscordEmbed

from fpdf import FPDF
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error, InputMediaPhoto, User
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.helpers import escape_markdown

# --- Konfiguration ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYPAL_USER = os.getenv("PAYPAL_USER")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
AGE_ANNA = os.getenv("AGE_ANNA", "18")
AGE_LUNA = os.getenv("AGE_LUNA", "21")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
NOTIFICATION_GROUP_ID = os.getenv("NOTIFICATION_GROUP_ID")

# NEU: Discord Webhook URLs aus Umgebungsvariablen
DISCORD_USER_LOG_WEBHOOK_URL = os.getenv("DISCORD_USER_LOG_WEBHOOK_URL")
DISCORD_STATS_WEBHOOK_URL = os.getenv("DISCORD_STATS_WEBHOOK_URL")


BTC_WALLET = "1FcgMLNBDLiuDSDip7AStuP19sq47LJB12"
ETH_WALLET = "0xeeb8FDc4aAe71B53934318707d0e9747C5c66f6e"

PRICES = {"bilder": {10: 5, 25: 10, 35: 15}, "videos": {10: 15, 25: 25, 35: 30}}
VOUCHER_FILE = "vouchers.json"
STATS_FILE = "stats.json"
MEDIA_DIR = "image"
DISCOUNT_MSG_HEADER = "--- BOT DISCOUNT DATA (DO NOT DELETE) ---"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- NEU: Discord Webhook Manager ---
class DiscordWebhookManager:
    """Verwaltet das Senden und Bearbeiten von Nachrichten an Discord-Webhooks."""
    
    @staticmethod
    def execute_webhook_action(webhook_url: str, message_id: str = None, embed: DiscordEmbed = None, content: str = None, action: str = 'send'):
        if not webhook_url:
            return None
        
        try:
            if action == 'edit' and message_id:
                webhook = DiscordWebhook(url=f"{webhook_url}/messages/{message_id}", content=content)
            else:
                webhook = DiscordWebhook(url=webhook_url, content=content)

            if embed:
                webhook.add_embed(embed)
                
            response = webhook.execute(remove_embeds=True) if action == 'execute' else webhook.edit() if action == 'edit' else webhook.execute()

            if response.status_code in [200, 201, 204]:
                if response.content:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        return None
                return None
            else:
                logger.error(f"Discord API Error ({response.status_code}): {response.content}")
                return None
        except Exception as e:
            logger.error(f"Failed to send/edit Discord message: {e}")
            return None

    @staticmethod
    def create_user_log_embed(user: User, user_data: dict, event_text: str) -> DiscordEmbed:
        """Erstellt ein ansprechendes Embed für das Nutzer-Log."""
        user_name = user.first_name
        user_id = user.id
        
        # Emojis für Status
        discount_emoji = "💸" if user_data.get("discount_sent") or "discounts" in user_data else ""
        banned_emoji = "🚫" if user_data.get("banned") else ""
        new_user_emoji = "🎉" if event_text.startswith("Bot gestartet (neuer Nutzer)") else "🔄"
        
        embed = DiscordEmbed(
            title=f"{new_user_emoji} Nutzer-Aktivität {discount_emoji}{banned_emoji}",
            description=f"**Letzte Aktion:** `{event_text}`",
            color="03b2f8"
        )
        embed.set_author(name=f"{user_name} ({user_id})", url=f"tg://user?id={user_id}")
        
        first_start_str = "N/A"
        if user_data.get("first_start"):
            first_start_str = datetime.fromisoformat(user_data["first_start"]).strftime('%d.%m.%Y %H:%M')
        
        viewed_sisters_list = user_data.get("viewed_sisters", [])
        viewed_sisters_str = f"({', '.join(s.upper() for s in sorted(viewed_sisters_list))})" if viewed_sisters_list else ""
        preview_clicks = user_data.get("preview_clicks", 0)
        
        payments = user_data.get("payments_initiated", [])
        payments_str = "\n".join(f"• {p}" for p in payments) if payments else "• Keine"
        
        embed.add_embed_field(name="Erster Start", value=f"`{first_start_str}`", inline=False)
        embed.add_embed_field(name="Vorschau-Klicks", value=f"`{preview_clicks}/25` {viewed_sisters_str}", inline=False)
        embed.add_embed_field(name="Bezahlversuche", value=f"```\n{payments_str}\n```", inline=False)
        
        embed.set_footer(text=f"Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        embed.set_thumbnail(url="https://i.imgur.com/7lsd68J.png") # Ein generisches User-Icon

        return embed
    
    @staticmethod
    def create_stats_dashboard_embed(stats: dict) -> DiscordEmbed:
        """Erstellt das Embed für das Statistik-Dashboard."""
        user_count = len(stats.get("users", {}))
        active_users_24h = 0
        now = datetime.now()
        for user_data in stats.get("users", {}).values():
            last_start_dt = datetime.fromisoformat(user_data.get("last_start", "1970-01-01T00:00:00"))
            if now - last_start_dt <= timedelta(hours=24):
                active_users_24h += 1
        
        events = stats.get("events", {})
        embed = DiscordEmbed(
            title="📊 Bot-Statistik Dashboard (Live)",
            color="2ecc71"
        )
        embed.set_footer(text=f"Letztes Update: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        
        embed.add_embed_field(name="👥 Nutzerübersicht", value=f"Gesamt: **{user_count}**\nAktiv (24h): **{active_users_24h}**\nStarts: **{events.get('start_command', 0)}**")
        embed.add_embed_field(name="💰 Bezahl-Interesse", value=f"PayPal: **{events.get('payment_paypal', 0)}**\nKrypto: **{events.get('payment_crypto', 0)}**\nGutschein: **{events.get('payment_voucher', 0)}**")
        embed.add_embed_field(name="🖱️ Klick-Verhalten", value=f"Vorschau (KS/GS): **{events.get('preview_ks', 0)}** / **{events.get('preview_gs', 0)}**\nPreise (KS/GS): **{events.get('prices_ks', 0)}** / **{events.get('prices_gs', 0)}**\n'Nächstes Bild': **{events.get('next_preview', 0)}**")
        
        return embed

# --- Hilfsfunktionen ---
def load_vouchers():
    try:
        with open(VOUCHER_FILE, "r") as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {"amazon": []}

def save_vouchers(vouchers):
    with open(VOUCHER_FILE, "w") as f: json.dump(vouchers, f, indent=2)

def load_stats():
    try:
        with open(STATS_FILE, "r") as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"pinned_message_id": None, "discount_message_id": None, "users": {}, "admin_logs": {}, "events": {}, "discord_message_ids": {}}

def save_stats(stats):
    with open(STATS_FILE, "w") as f: json.dump(stats, f, indent=4)

# --- Rabatt-Persistenz (unverändert) ---
async def save_discounts_to_telegram(context: ContextTypes.DEFAULT_TYPE):
    if not NOTIFICATION_GROUP_ID: return
    stats = load_stats(); discounts_to_save = {}
    for user_id, user_data in stats.get("users", {}).items():
        if "discounts" in user_data: discounts_to_save[user_id] = user_data["discounts"]
    json_string = json.dumps(discounts_to_save, indent=2); message_text = f"{DISCOUNT_MSG_HEADER}\n<tg-spoiler>{json_string}</tg-spoiler>"; discount_message_id = stats.get("discount_message_id")
    try:
        if discount_message_id: await context.bot.edit_message_text(chat_id=NOTIFICATION_GROUP_ID, message_id=discount_message_id, text=message_text, parse_mode='HTML')
        else: raise error.BadRequest("No discount message ID found")
    except error.BadRequest:
        logger.warning("Discount message not found or invalid, creating a new one.")
        try:
            sent_message = await context.bot.send_message(chat_id=NOTIFICATION_GROUP_ID, text=message_text, parse_mode='HTML')
            stats["discount_message_id"] = sent_message.message_id; save_stats(stats)
        except Exception as e: logger.error(f"Could not create a new discount persistence message: {e}")

async def load_discounts_from_telegram(application: Application):
    if not NOTIFICATION_GROUP_ID: logger.info("No notification group ID, skipping discount restore."); return
    logger.info("Attempting to restore discounts from Telegram message..."); stats = load_stats(); discount_message_id = stats.get("discount_message_id")
    if not discount_message_id: logger.warning("No discount message ID in stats.json. Cannot restore discounts."); return
    try:
        message = await application.bot.get_message(chat_id=NOTIFICATION_GROUP_ID, message_id=discount_message_id)
        json_match = re.search(r'<tg-spoiler>(.*)</tg-spoiler>', message.text_html, re.DOTALL)
        if not json_match: logger.error("Could not find spoiler tag in discount message."); return
        discounts_data = json.loads(json_match.group(1)); users_updated = 0
        for user_id, discounts in discounts_data.items():
            if user_id in stats["users"]: stats["users"][user_id]["discounts"] = discounts; users_updated += 1
        if users_updated > 0: save_stats(stats); logger.info(f"Successfully restored discounts for {users_updated} users.")
        else: logger.info("No discounts found in the persistence message to restore.")
    except Exception as e: logger.error(f"An unexpected error occurred during discount restore: {e}")

async def track_event(event_name: str, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if str(user_id) == ADMIN_USER_ID: return
    stats = load_stats(); stats["events"][event_name] = stats["events"].get(event_name, 0) + 1; save_stats(stats); await update_pinned_summary(context)

def is_user_banned(user_id: int) -> bool:
    stats = load_stats(); user_data = stats.get("users", {}).get(str(user_id), {}); return user_data.get("banned", False)

def get_discounted_price(base_price: int, discount_data: dict, package_key: str) -> int:
    if not discount_data: return -1
    discount_type = discount_data.get("type")
    
    if discount_type == "percent":
        value = discount_data.get("value", 0); new_price = base_price * (1 - value / 100); return ceil(new_price)
    elif discount_type == "euro_packages":
        packages = discount_data.get("packages", {});
        if package_key in packages: return max(1, base_price - packages[package_key])
    elif discount_type == "percent_packages":
        packages = discount_data.get("packages", {});
        if package_key in packages: value = packages[package_key]; new_price = base_price * (1 - value / 100); return ceil(new_price)
    return -1

def get_package_button_text(media_type: str, amount: int, user_id: int) -> str:
    stats = load_stats(); user_data = stats.get("users", {}).get(str(user_id), {}); base_price = PRICES[media_type][amount]; package_key = f"{media_type}_{amount}"
    label = f"{amount} {media_type.capitalize()}"
    discount_price = get_discounted_price(base_price, user_data.get("discounts"), package_key)
    if discount_price != -1: return f"{label} ~{base_price}~{discount_price}€ ✨"
    else: return f"{label} {base_price}€"

async def check_user_status(user_id: int, context: ContextTypes.DEFAULT_TYPE, ref_id: str = None):
    if str(user_id) == ADMIN_USER_ID: return "admin", False, None
    stats = load_stats(); user_id_str = str(user_id); now = datetime.now(); user_data = stats.get("users", {}).get(user_id_str)
    is_new_user = user_data is None
    if is_new_user:
        stats.get("users", {})[user_id_str] = {
            "first_start": now.isoformat(), "last_start": now.isoformat(), "discount_sent": False,
            "preview_clicks": 0, "viewed_sisters": [], "payments_initiated": [], "banned": False,
            "referrer_id": ref_id, "referrals": [], "successful_referrals": 0, "reward_triggered_for_referrer": False,
            "paypal_offer_sent": False
        }
        if ref_id and ref_id in stats["users"]: stats["users"][ref_id].setdefault("referrals", []).append(user_id_str)
        save_stats(stats); await update_pinned_summary(context); return "new", True, stats["users"][user_id_str]
    last_start_dt = datetime.fromisoformat(user_data.get("last_start"))
    if now - last_start_dt > timedelta(hours=24):
        stats["users"][user_id_str]["last_start"] = now.isoformat(); save_stats(stats); return "returning", True, stats["users"][user_id_str]
    stats["users"][user_id_str]["last_start"] = now.isoformat(); save_stats(stats); return "active", False, stats["users"][user_id_str]

async def send_or_update_admin_log(context: ContextTypes.DEFAULT_TYPE, user: User, event_text: str = ""):
    if str(user.id) == ADMIN_USER_ID: return
    user_id_str = str(user.id)
    stats = load_stats()
    user_data = stats.get("users", {}).get(user_id_str, {})
    
    # --- Telegram Logik (bestehend) ---
    if NOTIFICATION_GROUP_ID:
        admin_logs = stats.get("admin_logs", {})
        log_message_id = admin_logs.get(user_id_str, {}).get("message_id")
        user_mention = f"[{escape_markdown(user.first_name, version=2)}](tg://user?id={user.id})"
        discount_emoji = "💸" if user_data.get("discount_sent") or "discounts" in user_data else ""
        banned_emoji = "🚫" if user_data.get("banned") else ""
        first_start_str = "N/A"
        if user_data.get("first_start"): first_start_str = datetime.fromisoformat(user_data["first_start"]).strftime('%Y-%m-%d %H:%M')
        viewed_sisters_list = user_data.get("viewed_sisters", []); viewed_sisters_str = f"(Gesehen: {', '.join(s.upper() for s in sorted(viewed_sisters_list))})" if viewed_sisters_list else ""; preview_clicks = user_data.get("preview_clicks", 0); payments = user_data.get("payments_initiated", []); payments_str = "\n".join(f"   • {p}" for p in payments) if payments else "   • Keine"
        base_text = (f"👤 *Nutzer-Aktivität* {discount_emoji}{banned_emoji}\n\n" f"*Nutzer:* {user_mention} (`{user.id}`)\n" f"*Erster Start:* `{first_start_str}`\n\n" f"🖼️ *Vorschau-Klicks:* {preview_clicks}/25 {viewed_sisters_str}\n\n" f"💰 *Bezahlversuche*\n{payments_str}")
        final_text = f"{base_text}\n\n`Letzte Aktion: {event_text}`".strip()
        try:
            if log_message_id: await context.bot.edit_message_text(chat_id=NOTIFICATION_GROUP_ID, message_id=log_message_id, text=final_text, parse_mode='Markdown')
            else:
                sent_message = await context.bot.send_message(chat_id=NOTIFICATION_GROUP_ID, text=final_text, parse_mode='Markdown')
                admin_logs.setdefault(user_id_str, {})["message_id"] = sent_message.message_id; stats["admin_logs"] = admin_logs; save_stats(stats)
        except error.BadRequest as e:
            if "message to edit not found" in str(e):
                logger.warning(f"Admin log for user {user.id} not found (ID: {log_message_id}). Sending a new one.")
                try:
                    sent_message = await context.bot.send_message(chat_id=NOTIFICATION_GROUP_ID, text=final_text, parse_mode='Markdown')
                    admin_logs.setdefault(user_id_str, {})["message_id"] = sent_message.message_id; stats["admin_logs"] = admin_logs; save_stats(stats)
                except Exception as e_new: logger.error(f"Failed to send replacement admin log for user {user.id}: {e_new}")
            else: logger.error(f"BadRequest on admin log for user {user.id}: {e}")
        except error.TelegramError as e:
            if 'message is not modified' not in str(e): logger.warning(f"Temporary error updating admin log for user {user.id} (ID: {log_message_id}): {e}")

    # --- NEU: Discord Logik ---
    if DISCORD_USER_LOG_WEBHOOK_URL:
        discord_ids = stats.setdefault("discord_message_ids", {})
        discord_msg_id = discord_ids.get(user_id_str)
        
        embed = DiscordWebhookManager.create_user_log_embed(user, user_data, event_text)
        
        # Füge Buttons hinzu
        webhook = DiscordWebhook(url=DISCORD_USER_LOG_WEBHOOK_URL)
        webhook.add_embed(embed)
        webhook.add_content(
            f'[Telegram Profil](tg://user?id={user.id}) | [Nutzer Bannen](https://placeholder.url/ban?user_id={user.id}) | [Rabatt Senden](https://placeholder.url/discount?user_id={user.id})'
        )
        
        if discord_msg_id: # Nachricht bearbeiten
            webhook.url = f"{DISCORD_USER_LOG_WEBHOOK_URL}/messages/{discord_msg_id}"
            response = webhook.edit(remove_embeds=True)
        else: # Neue Nachricht senden
            response = webhook.execute(remove_embeds=True)
            if response.status_code in [200, 201] and response.content:
                try:
                    discord_ids[user_id_str] = response.json()['id']
                    stats["discord_message_ids"] = discord_ids
                    save_stats(stats)
                except (json.JSONDecodeError, KeyError):
                    logger.error("Could not parse Discord response to get message ID.")
        
        if response.status_code not in [200, 204]:
             logger.error(f"Discord API error for user log ({response.status_code}): {response.content}")


async def update_pinned_summary(context: ContextTypes.DEFAULT_TYPE):
    if not (NOTIFICATION_GROUP_ID or DISCORD_STATS_WEBHOOK_URL): return
    stats = load_stats()
    
    # --- Telegram Logik (bestehend) ---
    if NOTIFICATION_GROUP_ID:
        user_count = len(stats.get("users", {})); active_users_24h = 0; now = datetime.now()
        for user_data in stats.get("users", {}).values():
            last_start_dt = datetime.fromisoformat(user_data.get("last_start", "1970-01-01T00:00:00"))
            if now - last_start_dt <= timedelta(hours=24): active_users_24h += 1
        events = stats.get("events", {})
        text = (f"📊 *Bot-Statistik Dashboard*\n" f"🕒 _Letztes Update:_ `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n" f"👥 *Nutzerübersicht*\n" f"   • Gesamt: *{user_count}*\n" f"   • Aktiv (24h): *{active_users_24h}*\n" f"   • Starts: *{events.get('start_command', 0)}*\n\n" f"💰 *Bezahl-Interesse*\n" f"   • PayPal: *{events.get('payment_paypal', 0)}*\n" f"   • Krypto: *{events.get('payment_crypto', 0)}*\n" f"   • Gutschein: *{events.get('payment_voucher', 0)}*\n\n" f"🖱️ *Klick-Verhalten*\n" f"   • Vorschau (KS): *{events.get('preview_ks', 0)}*\n" f"   • Vorschau (GS): *{events.get('preview_gs', 0)}*\n" f"   • Preise (KS): *{events.get('prices_ks', 0)}*\n" f"   • Preise (GS): *{events.get('prices_gs', 0)}*\n" f"   • 'Nächstes Bild': *{events.get('next_preview', 0)}*\n" f"   • Paketauswahl: *{events.get('package_selected', 0)}*")
        pinned_id = stats.get("pinned_message_id")
        try:
            if pinned_id: await context.bot.edit_message_text(chat_id=NOTIFICATION_GROUP_ID, message_id=pinned_id, text=text, parse_mode='Markdown')
            else: raise error.BadRequest("Keine ID")
        except (error.BadRequest, error.Forbidden):
            logger.warning("Konnte Dashboard nicht bearbeiten, erstelle neu.")
            try:
                sent_message = await context.bot.send_message(chat_id=NOTIFICATION_GROUP_ID, text=text, parse_mode='Markdown')
                stats["pinned_message_id"] = sent_message.message_id; save_stats(stats)
                await context.bot.pin_chat_message(chat_id=NOTIFICATION_GROUP_ID, message_id=sent_message.message_id, disable_notification=True)
            except Exception as e_new: logger.error(f"Konnte Dashboard nicht erstellen/anpinnen: {e_new}")
    
    # --- NEU: Discord Logik ---
    if DISCORD_STATS_WEBHOOK_URL:
        discord_ids = stats.setdefault("discord_message_ids", {})
        dashboard_msg_id = discord_ids.get("stats_dashboard")
        
        embed = DiscordWebhookManager.create_stats_dashboard_embed(stats)
        
        if dashboard_msg_id: # Nachricht bearbeiten
            response = DiscordWebhookManager.execute_webhook_action(DISCORD_STATS_WEBHOOK_URL, message_id=dashboard_msg_id, embed=embed, action='edit')
        else: # Neue Nachricht senden
            response = DiscordWebhookManager.execute_webhook_action(DISCORD_STATS_WEBHOOK_URL, embed=embed, action='send')
            if response and 'id' in response:
                discord_ids["stats_dashboard"] = response['id']
                stats["discord_message_ids"] = discord_ids
                save_stats(stats)

# Restlicher Code bleibt unverändert...

# ... (kompletter Code von oben, bis zum main() Aufruf)
# (Stellen Sie sicher, dass alle Funktionen von `start` bis `post_init` hier eingefügt sind)

# [ HIER DEN RESTLICHEN CODE AUS DEINER bot.py EINFÜGEN ]
# (Von async def start(...) bis async def post_init(...))
# Es ist wichtig, den kompletten, funktionierenden Code zu übernehmen.


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    if WEBHOOK_URL:
        port = int(os.environ.get("PORT", 8443)); application.run_webhook(listen="0.0.0.0", port=port, url_path=BOT_TOKEN, webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    else:
        logger.info("Starte Bot im Polling-Modus"); application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
