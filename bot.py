import os
import logging
import random
import math
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from typing import Union
from pymongo import MongoClient
from telegram import (
    Update, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from telegram.error import BadRequest
from aiohttp import web
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import io
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('airtime_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot configuration
CONFIG = {
    'token': os.getenv('TELEGRAM_BOT_TOKEN'),
    'admin_ids': [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id],
    'welcome_image': os.getenv('WELCOME_IMAGE_URL', 'https://envs.sh/rXD.jpg'),
    'success_image': os.getenv('SUCCESS_IMAGE_URL', 'https://envs.sh/rX2.jpg'),  # Add your image URL here
    'tutorial_video': os.getenv('TUTORIAL_VIDEO_URL', 'https://www.youtube.com/@Freenethubtech')  # Add your YouTube tutorial URL
}

# Force Join Configuration
CHANNEL_USERNAMES = os.getenv("CHANNEL_USERNAMES", "@megahubbots, @Freenethubz, @smmserviceslogs").split(",")
CHANNEL_LINKS = os.getenv("CHANNEL_LINKS", "https://t.me/megahubbots, https://t.me/Freenethubz, https://t.me/smmserviceslogs").split(",")

# MongoDB connection
client = MongoClient(os.getenv('MONGODB_URI'))
db = client[os.getenv('DATABASE_NAME', 'AirtimePrankBot')]

# Collections
users_collection = db['users']
leaderboard_collection = db['leaderboard']
admins_collection = db['admins']

# Initialize database with admin user if empty
if admins_collection.count_documents({}) == 0 and os.getenv('ADMIN_IDS'):
    for admin_id in CONFIG['admin_ids']:
        admins_collection.update_one(
            {'user_id': admin_id},
            {'$set': {'user_id': admin_id}},
            upsert=True
        )

# Webhook configuration
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '') + WEBHOOK_PATH

# Welcome message
WELCOME_MESSAGE = """
🌟 𝗪ᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ Aɪʀᴛɪᴍᴇ Sᴇɴᴅᴇʀ Bᴏᴛ! 🌟

🎭 𝗧ʜɪꜱ ɪꜱ ᴀ ꜰᴜɴ ᴘʀᴀɴᴋ ᴛᴏᴏʟ ᴛʜᴀᴛ "ꜱᴇɴᴅꜱ" ᴀɪʀᴛɪᴍᴇ ᴛᴏ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀꜱ.

✨ 𝗤ᴜɪᴄᴋ Cᴏᴍᴍᴀɴᴅꜱ:
🔹 /sendairtime – Sᴛᴀʀᴛ ᴛʜᴇ ᴀɪʀᴛɪᴍᴇ ꜱᴇɴᴅɪɴɢ ᴘʀᴏᴄᴇꜱꜱ  
🔹 /howtouse – Dᴇᴛᴀɪʟᴇᴅ ɪɴꜱᴛʀᴜᴄᴛɪᴏɴꜱ  
🔹 /leaderboard – Tᴏᴘ ꜱᴇɴᴅᴇʀꜱ  
🔹 /contactus – Cᴏɴᴛᴀᴄᴛ ꜱᴜᴘᴘᴏʀᴛ

⚠️ 𝗡ᴏᴛᴇ: Tʜɪꜱ ɪꜱ ᴊᴜꜱᴛ ꜰᴏʀ ꜰᴜɴ! Nᴏ ʀᴇᴀʟ ᴀɪʀᴛɪᴍᴇ ɪꜱ ꜱᴇɴᴛ.
"""

# Animation frames
PROGRESS_FRAMES = [
"🟩⬜⬜⬜⬜ [13%] Iɴɪᴛɪᴀʟɪᴢɪɴɢ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ...",
"🟩🟩⬜⬜⬜ [27%] Cᴏɴɴᴇᴄᴛɪɴɢ ᴛᴏ ᴍᴏʙɪʟᴇ ɴᴇᴛᴡᴏʀᴋ...",
"🟩🟩🟩⬜⬜ [41%] Vᴇʀɪꜰʏɪɴɢ ʀᴇᴄɪᴘɪᴇɴᴛ...",
"🟩🟩🟩🟩⬜ [63%] Pʀᴏᴄᴇꜱꜱɪɴɢ ᴘᴀʏᴍᴇɴᴛ...",
"🟩🟩🟩🟩🟩 [100%] Tʀᴀɴꜱᴀᴄᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ!",
]

NETWORKS = ["Airtel", "MTN", "Africell", "Vodafone", "Uganda Telecom"]
COUNTRIES = {
    "UG": "Uganda 🇺🇬",
    "KE": "Kenya 🇰🇪", 
    "TZ": "Tanzania 🇹🇿",
    "RW": "Rwanda 🇷🇼"
}

def get_current_time():
    now = datetime.now()
    return {
        'weekday': now.strftime("%A"),
        'time': now.strftime("%I:%M %p")
    }

def detect_network_and_country(phone):
    """Detect network and country based on phone number prefix."""
    # Uganda
    if phone.startswith("+256") or phone.startswith("256"):
        country = "Uganda 🇺🇬"
        # Airtel: 075, 070, 074, 020; MTN: 077, 078, 039; Africell: 079; UTL: 071, 041; Vodafone: 072
        prefix = re.sub(r"^\+?256", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("75") or prefix.startswith("70") or prefix.startswith("74") or prefix.startswith("20"):
            network = "Airtel"
        elif prefix.startswith("77") or prefix.startswith("78") or prefix.startswith("39"):
            network = "MTN"
        elif prefix.startswith("79"):
            network = "Africell"
        elif prefix.startswith("71") or prefix.startswith("41"):
            network = "Uganda Telecom"
        elif prefix.startswith("72"):
            network = "Vodafone"
        else:
            network = "Unknown"
    # Kenya
    elif phone.startswith("+254") or phone.startswith("254"):
        country = "Kenya 🇰🇪"
        prefix = re.sub(r"^\+?254", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("7"):
            network = "Safaricom"
        elif prefix.startswith("10") or prefix.startswith("11"):
            network = "Airtel"
        elif prefix.startswith("20"):
            network = "Telkom"
        else:
            network = "Unknown"
    # Tanzania
    elif phone.startswith("+255") or phone.startswith("255"):
        country = "Tanzania 🇹🇿"
        prefix = re.sub(r"^\+?255", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("65") or prefix.startswith("68"):
            network = "Airtel"
        elif prefix.startswith("75") or prefix.startswith("76"):
            network = "Vodacom"
        elif prefix.startswith("71"):
            network = "Tigo"
        else:
            network = "Unknown"
    # Rwanda
    elif phone.startswith("+250") or phone.startswith("250"):
        country = "Rwanda 🇷🇼"
        prefix = re.sub(r"^\+?250", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("78") or prefix.startswith("79"):
            network = "MTN"
        elif prefix.startswith("72"):
            network = "Airtel"
        else:
            network = "Unknown"

        # Ethiopia
    elif phone.startswith("+251") or phone.startswith("251"):
        country = "Ethiopia 🇪🇹"
        prefix = re.sub(r"^\+?251", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("91") or prefix.startswith("90") or prefix.startswith("96"):
            network = "Ethio Telecom"
        else:
            network = "Unknown"
    # Nigeria
    elif phone.startswith("+234") or phone.startswith("234"):
        country = "Nigeria 🇳🇬"
        prefix = re.sub(r"^\+?234", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith(("701", "702", "703", "704", "705", "706", "707", "708", "709")):
            network = "MTN or Glo or Airtel or 9mobile (check exact prefix)"
        elif prefix.startswith(("802", "803", "804", "805", "806", "807", "808", "809")):
            network = "MTN or Glo or Airtel (legacy numbers)"
        else:
            network = "Unknown"
    # Ghana
    elif phone.startswith("+233") or phone.startswith("233"):
        country = "Ghana 🇬🇭"
        prefix = re.sub(r"^\+?233", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("24") or prefix.startswith("54") or prefix.startswith("55"):
            network = "MTN"
        elif prefix.startswith("20") or prefix.startswith("50"):
            network = "Vodafone"
        elif prefix.startswith("26") or prefix.startswith("56"):
            network = "AirtelTigo"
        else:
            network = "Unknown"
    # Zimbabwe
    elif phone.startswith("+263") or phone.startswith("263"):
        country = "Zimbabwe 🇿🇼"
        prefix = re.sub(r"^\+?263", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("71"):
            network = "Econet"
        elif prefix.startswith("73"):
            network = "Telecel"
        elif prefix.startswith("77"):
            network = "NetOne"
        else:
            network = "Unknown"
    # Mali
    elif phone.startswith("+223") or phone.startswith("223"):
        country = "Mali 🇲🇱"
        prefix = re.sub(r"^\+?223", "", phone)
        prefix = prefix.lstrip("0")
        if prefix.startswith("7"):
            network = "Orange Mali"
        elif prefix.startswith("6"):
            network = "Malitel"
        else:
            network = "Unknown"
    else:
        country = "Unknown"
        network = "Unknown"
    return network, country

def generate_airtime_message(phone, amount, name):
    network, country = detect_network_and_country(phone)
    time_info = get_current_time()
    return f"""
💳  𝘼𝙞𝙧𝙩𝙞𝙢𝙚 𝙎𝙚𝙣𝙩 𝙎𝙪𝙘𝙘𝙚𝙨𝙨𝙛𝙪𝙡 !
━━━━━━━━━━━━━━━━━━━━
│▸ 🪪 Nᴀᴍᴇ: {name}
│▸ 📱 Pʜᴏɴᴇ: {phone}
│▸ 📡 Nᴇᴛᴡᴏʀᴋ: {network}
│▸ 🌍 Cᴏᴜɴᴛʀʏ: {country}
│▸ ⭐ Aɪʀᴛɪᴍᴇ Aᴍᴏᴜɴᴛ: {amount:,}
│▸ ☀️ Wᴇᴇᴋᴅᴀʏ: {time_info['weekday']}
│▸ ⏰ Tɪᴍᴇ: {time_info['time']}
╰────────────···▸▸

✅ Tʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜꜱɪɴɢ ᴏᴜʀ Sᴇʀᴠɪᴄᴇ!
▬▬▬▬「 ᴩᴏᴡᴇʀᴇᴅ ʙy 」▬▬▬▬
         • @MEGAHUBBOTS •
"""

# Database Management Functions
def add_user(user):
    """Add user to database if not exists"""
    users_collection.update_one(
        {'user_id': user.id},
        {'$set': {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'join_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'airtime_sent': 0,
            'transactions': 0
        }},
        upsert=True
    )

def is_admin(user_id):
    """Check if user is admin"""
    return admins_collection.count_documents({'user_id': user_id}) > 0 or user_id in CONFIG['admin_ids']

def add_airtime_transaction(user_id, username, phone_number, amount):
    """Add airtime transaction to leaderboard"""
    transaction = {
        'user_id': user_id,
        'username': username,
        'phone_number': phone_number,
        'amount': amount,
        'transaction_date': datetime.now(),
        'txn_id': f"TX{random.randint(100000, 999999)}"
    }
    
    leaderboard_collection.insert_one(transaction)
    
    # Update user stats
    users_collection.update_one(
        {'user_id': user_id},
        {'$inc': {'airtime_sent': amount, 'transactions': 1}}
    )

def get_leaderboard():
    """Get top 10 senders by total amount sent"""
    pipeline = [
        {"$group": {
            "_id": "$user_id",
            "username": {"$first": "$username"},
            "total_amount": {"$sum": "$amount"}
        }},
        {"$sort": {"total_amount": -1}},
        {"$limit": 10}
    ]
    return list(leaderboard_collection.aggregate(pipeline))

def get_user_count():
    """Get total number of users"""
    return users_collection.count_documents({})

def get_all_users():
    """Get all user IDs for broadcasting"""
    return [user['user_id'] for user in users_collection.find({}, {'user_id': 1})]

async def is_member_of_channels(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is a member of all required channels."""
    for channel in CHANNEL_USERNAMES:
        channel = channel.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        try:
            chat_member = await context.bot.get_chat_member(channel, user_id)
            # Acceptable statuses: member, administrator, creator
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False
        except BadRequest as e:
            # If bot is not admin or can't access the channel, log the error
            logger.warning(f"Error checking membership for {channel}: {e}")
            return False
    return True

async def send_force_join_message(update: Update):
    """Send force join message with buttons for all channels (without @ in button text)."""
    buttons = [
        [InlineKeyboardButton(f"Join {CHANNEL_USERNAMES[i].strip().lstrip('@')}", url=CHANNEL_LINKS[i].strip())]
        for i in range(len(CHANNEL_USERNAMES))
    ]
    buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="verify_join")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "🔒 *Aᴄᴇꜱꜱ Rᴇꜱᴛʀɪᴄᴛᴇᴅ* 🔒\n\n"
        "Tᴏ ᴜꜱᴇ ᴛʜɪꜱ ʙᴏᴛ, ʏᴏᴜ ᴍᴜꜱᴛ ᴊᴏɪɴ ᴏᴜʀ ᴏꜰꜰɪᴄɪᴀʟ ᴄʜᴀɴɴᴇʟꜱ:\n\n"
        "👉 Tᴀᴘ ᴇᴀᴄʜ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ\n"
        "👉 Tʜᴇɴ ᴄʟɪᴄᴋ 'I'ᴠᴇ Jᴏɪɴᴇᴅ' ᴛᴏ ᴠᴇʀɪꜰʏ",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join verification callback"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if await is_member_of_channels(user_id, context):
        await query.answer("✅ Verification successful! You can now use the bot.")
        await query.message.edit_text(
            "✅ *Vᴇʀɪꜰɪᴄᴀᴛɪᴏɴ Cᴏᴍᴘʟᴇᴛᴇ!*\n\n"
            "Yᴏᴜ'ᴠᴇ ꜱᴜᴄᴄᴇꜱꜰᴜʟʟʏ ᴊᴏɪɴᴇᴅ ᴀʟʟ ʀᴇQᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟꜱ.\n"
            "Uꜱᴇ /start ᴛᴏ ʙᴇɡɪɴ!",
            parse_mode="Markdown"
        )
    else:
        await query.answer("❌ Yᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴀʟʟ ᴄʜᴀɴɴᴇʟꜱ ʏᴇᴛ!", show_alert=True)

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command with welcome image."""
    user = update.effective_user
    add_user(user)
    
    if not await is_member_of_channels(user.id, context):
        await send_force_join_message(update)
        return

    # Send notification to channel
    await send_notification(context.bot, user.id, user.username, "Started the bot")

    keyboard = [
        [InlineKeyboardButton("💸 Send Airtime", callback_data="send_airtime")],
    ]
    
    try:
        await context.bot.send_photo(
            chat_id=user.id,
            photo=CONFIG['welcome_image'],
            caption=WELCOME_MESSAGE,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error sending welcome image: {e}")
        await update.message.reply_text(
            WELCOME_MESSAGE,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def send_airtime(update: Union[Update, CallbackQueryHandler], context: ContextTypes.DEFAULT_TYPE):
    """Handle airtime sending process."""
    user = update.effective_user
    
    if not await is_member_of_channels(user.id, context):
        await send_force_join_message(update)
        return

    # Clear any existing state
    context.user_data.clear()
    
    # Set the new state
    context.user_data["awaiting_airtime_details"] = True
    
    await context.bot.send_message(
        chat_id=user.id,
        text="📱 *Aɪʀᴛɪᴍᴇ ꜱᴇɴᴅɪɴɢ ᴘʀᴏᴄᴇꜱꜱ*\n\n"
             "Pʟᴇᴀꜱᴇ ꜱᴇɴᴅ ᴛʜᴇ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ ᴡɪᴛʜ ᴄᴏᴜɴᴛʀʏ ᴄᴏᴅᴇ ᴀɴᴅ ᴀᴍᴏᴜɴᴛ:\n"
             "Exᴀᴍᴘʟᴇ: `+256751722034 5000`\n\n"
             "🔒 Wᴇ ᴅᴏɴ'ᴛ ꜱᴛᴏʀᴇ ᴏʀ ᴜꜱᴇ ʀᴇᴀʟ ɴᴜᴍʙᴇʀꜱ",
        parse_mode="Markdown"
    )

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle leaderboard callback from inline button or command."""
    query = getattr(update, "callback_query", None)
    leaderboard_data = get_leaderboard()
    leaderboard_text = "🏆 Tᴏᴘ 10 ꜱᴇɴᴅᴇʀꜱ\n━━━━━━━━━━━━━━━━━\n"
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    for idx, entry in enumerate(leaderboard_data):
        username = entry.get('username', 'Anonymous')
        if not username or username == 'None':
            username = "Anonymous"
        username = str(username).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
        leaderboard_text += f"{medals[idx]} {username}: {entry['total_amount']:,} UGX\n"
    if not leaderboard_data:
        leaderboard_text += "\nLᴇᴀᴅᴇʀʙᴏᴀʀᴅ ɪꜱ ᴇᴍᴘᴛʏ! ʙᴇ ᴛʜᴇ ꜰɪʀꜱᴛ ᴡɪᴛʜ /sendairtime"
    # If called from button
    if query:
        await query.answer()
        # Only edit if the message exists and is not empty
        if query.message and (query.message.text or query.message.caption):
            await query.message.edit_text(leaderboard_text)
        else:
            await query.message.reply_text(leaderboard_text)
    else:
        # Called from /leaderboard command
        await update.message.reply_text(leaderboard_text)

async def how_to_use(update: Union[Update, CallbackQueryHandler], context: ContextTypes.DEFAULT_TYPE):
    """Handle how-to-use command from button or command."""
    instructions = """
📘 Aɪʀᴛɪᴍᴇ Sᴇɴᴅᴇʀ Bᴏᴛ Gᴜɪᴅᴇ 📘

1️⃣ Gᴇᴛᴛɪɴɡ Sᴛᴀʀᴛᴇᴅ
- Use /start to begin
- Jᴏɪɴ ʀᴇQᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟꜱ ɪꜰ ᴘʀᴏᴍᴘᴛᴇᴅ

2️⃣ Sᴇɴᴅɪɴɡ Pʀᴏᴄᴇꜱꜱ
- Use /sendairtime
- Eɴᴛᴇʀ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ ᴀɴᴅ ᴀᴍᴏᴜɴᴛ
- Wᴀᴛᴄʜ ᴛʜᴇ ᴍᴀɡɪᴄ ʜᴀᴘᴘᴇɴ!

3️⃣ Fᴇᴀᴛᴜʀᴇꜱ
- Fᴜɴ ᴀɪʀᴛɪᴍᴇ ꜱᴇɴᴅɪɴɡ ꜱɪᴍᴜʟᴀᴛɪᴏɴ
- Lᴇᴀᴅᴇʀʙᴏᴀʀᴅ ᴛʀᴀᴄᴋɪɴɢ
- Rᴇɡᴜʟᴀʀ ᴜᴘᴅᴀᴛᴇꜱ

4️⃣ Iᴍᴘᴏʀᴛᴀɴᴛ Nᴏᴛᴇꜱ
- Tʜɪꜱ ɪꜱ ᴊᴜꜱᴛ ꜰᴏʀ ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ
- Nᴏ ʀᴇᴀʟ ᴀɪʀᴛɪᴍᴇ ɪꜱ ꜱᴇɴᴛ
- Nᴏ ᴘᴇʀꜱᴏɴᴀʟ ᴅᴀᴛᴀ ɪꜱ ꜱᴛᴏʀᴇᴅ

🎉 Eɴᴊᴏʏ ᴛʜᴇ ᴇxᴘᴇʀɪᴇɴᴄᴇ!
5️⃣ Fᴏʀ Mᴏʀᴇ Hᴇʟᴘ
"""
    
    keyboard = [
        [InlineKeyboardButton("📺 Wᴀᴛᴄʜ Tᴜᴛᴏʀɪᴀʟ", url=CONFIG['tutorial_video'])]
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            instructions,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            instructions,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def contact_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced contact us command."""
    keyboard = [
        [InlineKeyboardButton("📩 Message Admin", url="https://t.me/Silando")],
        [InlineKeyboardButton("📢 Announcements", url="https://t.me/megahubbots")],
        [InlineKeyboardButton("💬 Support Channel", url="https://t.me/Freenethubz")]
    ]
    
    contact_text = """
📞 Cᴏɴᴛᴀᴄᴛ Iɴꜰᴏʀᴍᴀᴛɪᴏɴ 📞

🔹 Eᴍᴀɪʟ: freenethubbusiness@gmail.com  
🔹 Bᴜꜱɪɴᴇꜱꜱ Hᴏᴜʀꜱ: 9AM - 5PM (EAT)

📌 Fᴏʀ:
- Bᴜꜱɪɴᴇꜱꜱ ɪɴQᴜɪʀɪᴇꜱ  
- Bᴜɡ ʀᴇᴘᴏʀᴛꜱ  
- Fᴇᴀᴛᴜʀᴇ ʀᴇQᴜᴇꜱᴛꜱ

🚫 Pʟᴇᴀꜱᴇ ᴅᴏɴ'ᴛ ꜱᴘᴀᴍ!

━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(
        contact_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced stats command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *🅐🅒🅒🅔🅢🅢 🅓🅔🅝🅘🅔🅓*", parse_mode="Markdown")
        return

    user_count = get_user_count()
    transactions_count = leaderboard_collection.count_documents({})
    total_airtime = leaderboard_collection.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]).next().get('total', 0)
    
    stats_text = """
📈 Bᴏᴛ Sᴛᴀᴛɪꜱᴛɪᴄꜱ Dᴀꜱʜʙᴏᴀʀᴅ 📈
━━━━━━━━━━━━━━━━━━━━━━━
👥 Uꜱᴇʀꜱ:
├─ Tᴏᴛᴀʟ: {}
└─ Aᴄᴛɪᴠᴇ Tᴏᴅᴀʏ: {}

💸 Tʀᴀɴꜱᴀᴄᴛɪᴏɴꜱ:
├─ Tᴏᴛᴀʟ: {}
└─ Tᴏᴛᴀʟ Aɪʀᴛɪᴍᴇ: {:,}

⚙️ Sʏꜱᴛᴇᴍ:
├─ Uᴘᴛɪᴍᴇ: 99.9%
└─ Sᴛᴀᴛᴜꜱ: Oᴘᴇʀᴀᴛɪᴏɴᴀʟ
━━━━━━━━━━━━━━━━━━━━━━━
""".format(
        user_count,
        users_collection.count_documents({"join_date": {"$gte": datetime.now().strftime('%Y-%m-%d')}}),
        transactions_count,
        total_airtime
    )

    await update.message.reply_text(stats_text, parse_mode="Markdown")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast command to send a message to all users."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *🅐🅒🅒🅔🅢🅢 🅓🅔🅝🅘🅔🅓*", parse_mode="Markdown")
        return

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]]
    await update.message.reply_text(
        "📢 *Bʀᴏᴀᴅᴄᴀꜱᴛ Mᴏᴅᴇ Eɴᴀʙʟᴇᴅ*\n\n"
        "Pʟᴇᴀꜱᴇ sᴇɴᴅ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ bʀᴏᴀᴅᴄᴀꜱᴛ ᴛᴏ ᴀʟʟ ᴜꜱᴇʀꜱ.\n\n"
        "Iꜣ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴀɴᴄᴇʟ, ᴄʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Set state to indicate we're waiting for broadcast message
    context.user_data["awaiting_broadcast"] = True

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the actual broadcast message."""
    if not is_admin(update.effective_user.id):
        return

    # Only process if we're in broadcast mode
    if context.user_data.get("awaiting_broadcast"):
        # Clear the state first in case something goes wrong
        context.user_data["awaiting_broadcast"] = False
        
        # Get all users
        user_ids = get_all_users()
        total_users = len(user_ids)
        success = 0
        failures = 0
        
        # Send initial processing message
        processing_msg = await update.message.reply_text(
            f"📤 Broadcasting to {total_users} users...",
            parse_mode="Markdown"
        )
        
        # Broadcast the message
        for user_id in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=update.message.text,
                    parse_mode="Markdown"
                )
                success += 1
                await asyncio.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.warning(f"Failed to send to {user_id}: {e}")
                failures += 1
        
        # Update processing message with results
        await processing_msg.edit_text(
            f"📊 *Bʀᴏᴀᴅᴄᴀꜱᴛ Rᴇꜱᴜʟᴛꜱ*\n\n"
            f"✅ Sᴜᴄᴄᴇꜱꜱ: {success}\n"
            f"❌ Fᴀɪʟᴜʀᴇꜱ: {failures}\n"
            f"📩 Tᴏᴛᴀʟ Sᴇɴᴛ: {success + failures}\n",
            parse_mode="Markdown"
        )

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the broadcast process."""
    query = update.callback_query
    context.user_data["awaiting_broadcast"] = False
    await query.answer("Broadcast canceled.")
    await query.message.edit_text("📢 *Broadcast Canceled*", parse_mode="Markdown")

async def handle_airtime_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's airtime details input."""
    logger.info(f"Handling message: {update.message.text}")
    logger.info(f"Current state: awaiting_airtime_details={context.user_data.get('awaiting_airtime_details')}")
    if context.user_data.get("awaiting_airtime_details"):
        try:
            parts = update.message.text.split()
            if len(parts) != 2:
                raise ValueError("Invalid format")
                
            phone_number = parts[0]
            amount = int(parts[1])
            
            if amount <= 0:
                raise ValueError("Amount must be positive")
                
            user = update.effective_user
            context.user_data["awaiting_airtime_details"] = False
            add_airtime_transaction(user.id, user.username, phone_number, amount)

            # Send notification to channel
            await send_notification(context.bot, user.id, user.username, "Sent Airtime", phone=phone_number, amount=amount)

            # Enhanced sending animation with progress bar
            progress_msg = await update.message.reply_text("🔄 *Starting Airtime Transfer...*", parse_mode="Markdown")
            
            for i in range(1, 101):
                await asyncio.sleep(0.01)
                percentage = i
                progress = "[{0}{1}] \n<b>• Percentage :</b> {2}%\n".format(
                    ''.join(["▰" for _ in range(math.floor(percentage / 10))]),
                    ''.join(["▱" for _ in range(10 - math.floor(percentage / 10))]),
                    round(percentage, 2))
                
                try:
                    await progress_msg.edit_text(
                        f"💸 *Sending {amount:,} UGX to {phone_number}*\n\n{progress}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error updating progress: {e}")

            # Send success message with image
            try:
                await context.bot.send_photo(
                    chat_id=user.id,
                    photo=CONFIG['success_image'],
                    caption=generate_airtime_message(phone_number, amount, user.first_name or "User"),
                    parse_mode="Markdown"
                )
                await progress_msg.delete()
            except Exception as e:
                logger.error(f"Error sending success image: {e}")
                await progress_msg.edit_text(
                    generate_airtime_message(phone_number, amount, user.first_name or "User"),
                    parse_mode="Markdown"
                )

        except ValueError as e:
            await update.message.reply_text(
                "❌ Iɴᴠᴀʟɪᴅ ꜰᴏʀᴍᴀᴛ. Pʟᴇᴀꜱᴇ ꜱᴇɴᴅ:\n"
                "Pʜᴏɴᴇ Nᴜᴍʙᴇʀ ᴀᴍᴏᴜɴᴛ\n"
                "Exᴀᴍᴘʟᴇ: `+256751722034 5000`",
                parse_mode="Markdown"
            )

# Notification channel (set this in your .env as well)
NOTIFICATION_CHANNEL = os.getenv('NOTIFICATION_CHANNEL', '@smmserviceslogs')

# --- Notification Functions (copied from MULTI-AI-V3.py) ---

async def get_profile_photo(bot, user_id):
    """Download and process profile photo"""
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos.photos:
            raise Exception("No profile photo available")
        photo_file = await bot.get_file(photos.photos[0][-1].file_id)
        photo_bytes = await photo_file.download_as_bytearray()
        original_img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        # Create circular mask
        size = (500, 500)
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size[0], size[1]), fill=255)
        # Resize and apply mask
        img = ImageOps.fit(original_img, size, method=Image.LANCZOS)
        img.putalpha(mask)
        return img
    except Exception as e:
        logger.warning(f"Using default profile photo: {e}")
        # Create default gray circle (500x500)
        img = Image.new("RGBA", (500, 500), (70, 70, 70, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((0, 0, 500, 500), fill=(100, 100, 100, 255))
        return img

async def generate_notification_image(bot, user_img, user_name, bot_name, action):
    """Generate a pro-quality notification image."""
    try:
        # Get bot profile photo
        bot_img = await get_profile_photo(bot, bot.id)
        # Create base image with rich gradient background
        width, height = 800, 400
        bg = Image.new("RGB", (width, height), (30, 30, 45))
        gradient = Image.new("L", (1, height), color=0xFF)
        for y in range(height):
            gradient.putpixel((0, y), int(255 * (1 - y/height)))
        alpha_gradient = gradient.resize((width, height))
        black_img = Image.new("RGB", (width, height), color=(10, 10, 25))
        bg = Image.composite(bg, black_img, alpha_gradient)
        draw = ImageDraw.Draw(bg)
        # Fonts - added fallback for each font individually
        try:
            title_font = ImageFont.truetype("arialbd.ttf", 40)
        except:
            title_font = ImageFont.load_default().font_variant(size=40)
        try:
            name_font = ImageFont.truetype("arialbd.ttf", 28)
        except:
            name_font = ImageFont.load_default().font_variant(size=28)
        try:
            action_font = ImageFont.truetype("arialbd.ttf", 24)
        except:
            action_font = ImageFont.load_default().font_variant(size=24)
        # Draw top title
        draw.text((width // 2, 40), "NEW USER ACTIVITY", font=title_font,
                  fill="white", anchor="mm")
        # Helper to draw glowing circular image
        def draw_glowing_circle(base, img, pos, size, glow_color=(255, 215, 0)):
            glow = Image.new("RGBA", (size + 40, size + 40), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            center = (glow.size[0] // 2, glow.size[1] // 2)
            for radius in range(size // 2 + 10, size // 2 + 20):
                glow_draw.ellipse([
                    center[0] - radius, center[1] - radius,
                    center[0] + radius, center[1] + radius
                ], fill=glow_color + (10,), outline=None)
            glow = glow.filter(ImageFilter.GaussianBlur(8))
            black_img = Image.new("RGB", (width, height), color=(10, 10, 25))
            bg = Image.composite(bg, black_img, alpha_gradient)
            base.paste(glow, (pos[0] - 20, pos[1] - 20), glow)
            # Golden ring
            ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            ring_draw = ImageDraw.Draw(ring)
            ring_draw.ellipse((0, 0, size - 1, size - 1), outline=(255, 215, 0), width=6)
            # Add mask to image (ensure we're working with RGBA)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            img = img.resize((size, size))
            mask = Image.new('L', (size, size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, size, size), fill=255)
            img.putalpha(mask)
            base.paste(img, pos, img)
            base.paste(ring, pos, ring)
        # Paste profile images
        user_pos = (130, 120)
        bot_pos = (520, 120)
        draw_glowing_circle(bg, user_img, user_pos, 150)
        draw_glowing_circle(bg, bot_img, bot_pos, 150)
        # Draw usernames (with text length safety)
        max_name_length = 15
        safe_user_name = (user_name[:max_name_length] + '..') if len(user_name) > max_name_length else user_name
        safe_bot_name = (bot_name[:max_name_length] + '..') if len(bot_name) > max_name_length else bot_name
        draw.text((user_pos[0] + 75, 290), safe_user_name, font=name_font,
                  fill="white", anchor="ma")
        draw.text((bot_pos[0] + 75, 290), safe_bot_name, font=name_font,
                  fill="white", anchor="ma")
        # Draw action in the middle (with safety check)
        max_action_length = 30
        safe_action = (action[:max_action_length] + '..') if len(action) > max_action_length else action
        draw.text((width // 2, 330), f"Action: {safe_action}", font=action_font,
                  fill=(255, 215, 0), anchor="ma")
        # Bottom banner
        draw.rectangle([0, 370, width, 400], fill=(255, 215, 0))
        draw.text((width // 2, 385), "Powered by Airtime Bot", font=name_font,
                  fill=(30, 30, 30), anchor="mm")
        # Save to bytes
        img_byte_arr = io.BytesIO()
        bg.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr
    except Exception as e:
        logger.warning(f"Image generation error: {e}")
        return None

async def send_notification(bot, user_id, username, action, phone=None, amount=None):
    """Send notification to channel with generated image and styled caption"""
    try:
        user_img = await get_profile_photo(bot, user_id)
        bot_info = await bot.get_me()
        image_bytes = await generate_notification_image(bot, user_img, username, bot_info.first_name, action)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Vɪꜱɪᴛ Bᴏᴛ", url=f"https://t.me/{bot_info.username}")]
        ])
        caption = f"""⭐️ ｢Uꜱᴇʀ Aᴄᴛɪᴠɪᴛʏ Nᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ 」⭐️
━━━━━━━━•❅•°•❈•°•❅•━━━━━━━━
➠ 🕵🏻‍♂️ Uꜱᴇʀɴᴀᴍᴇ: @{username or 'Not set'}
━━━━━━━━━━━━━━━━━━━━━━━
➠ 🆔 Uꜱᴇʀ Iᴅ: {user_id}
━━━━━━━━━━━━━━━━━━━━━━━
➠ 📦 Aᴄᴛɪᴏɴ: {action}"""
        if phone and amount:
            caption += f"\n━━━━━━━━━━━━━━━━━━━━━━━\n➠ 📱 Pʜᴏɴᴇ: <code>{phone}</code>\n➠ 💸 Aᴍᴏᴜɴᴛ: <b>{amount:,} UGX</b>"
        caption += f"""
━━━━━━━━━━━━━━━━━━━━━━━
➠ ⏰ Tɪᴍᴇ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━
➠ 🤖 <b>Bᴏᴛ:</b> @{bot_info.username}
━━━━━━━━•❅•°•❈•°•❅•━━━━━━━━"""
        if image_bytes:
            await bot.send_photo(
                chat_id=NOTIFICATION_CHANNEL,
                photo=image_bytes,
                caption=caption,
                parse_mode='HTML',
                reply_markup=keyboard
            )
    except Exception as e:
        logger.warning(f"Error sending notification: {str(e)}")

# Main application setup
def main():
    """Run the bot."""
    application = Application.builder().token(CONFIG['token']).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sendairtime", send_airtime))
    application.add_handler(CommandHandler("leaderboard", show_leaderboard))
    application.add_handler(CommandHandler("howtouse", how_to_use))
    application.add_handler(CommandHandler("contactus", contact_us))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    application.add_handler(CallbackQueryHandler(send_airtime, pattern="^send_airtime$"))
    application.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^show_leaderboard$"))
    application.add_handler(CallbackQueryHandler(how_to_use, pattern="^how_to_use$"))
    application.add_handler(CallbackQueryHandler(cancel_broadcast, pattern="^cancel_broadcast$"))
    
    # Message handlers - FIXED ORDER
    # First check for airtime details
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_airtime_details
    ))
    
    # Then check for broadcast messages
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_broadcast_message
    ))
    
    # Start the bot
    if os.getenv('RENDER'):
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=WEBHOOK_URL
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
