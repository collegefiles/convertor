import os
import logging
import json
import threading
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from pydub import AudioSegment
from io import BytesIO
import instaloader
from uuid import uuid4
from datetime import datetime
import time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = "8153196269:AAFKqb9ztv9fOQuaTMN6DnQ29FLO7EDnxnE"
TARGET_CHANNEL = "@memize"
AUTHORIZED_USERS = [6897230899]  # Replace with your user ID

# Initialize Instaloader
L = instaloader.Instaloader()

# Data storage
USER_DATA_FILE = "user_data.json"
LINKS_FILE = "user_links.json"

# Load existing data
try:
    with open(USER_DATA_FILE, "r") as f:
        user_data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    user_data = {}

try:
    with open(LINKS_FILE, "r") as f:
        user_links = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    user_links = {}

# Helper functions
async def save_user_data(user_id: int, username: str = None, first_name: str = None):
    """Save user data to file"""
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {
            "first_seen": datetime.now().isoformat(),
            "username": username,
            "first_name": first_name,
            "last_interaction": datetime.now().isoformat()
        }
    else:
        user_data[str(user_id)]["last_interaction"] = datetime.now().isoformat()
    
    with open(USER_DATA_FILE, "w") as f:
        json.dump(user_data, f, indent=2)

async def save_user_link(user_id: int, link: str, link_type: str):
    """Save user links to file"""
    if str(user_id) not in user_links:
        user_links[str(user_id)] = []
    
    user_links[str(user_id)].append({
        "link": link,
        "type": link_type,
        "timestamp": datetime.now().isoformat()
    })
    
    with open(LINKS_FILE, "w") as f:
        json.dump(user_links, f, indent=2)

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    await update.message.reply_text(
        "Hi! I'm your media bot. I can:\n"
        "1. Convert videos to MP3 - reply to a video with /convert\n"
        "2. Download Instagram reels - send /reel <URL>"
    )

async def convert_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert video to MP3"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Please reply to a video file with /convert")
        return
    
    try:
        video_file = await update.message.reply_to_message.video.get_file()
        unique_id = uuid4().hex
        output_filename = f"converted_{unique_id}.mp3"
        
        status_msg = await update.message.reply_text("⬇️ Downloading video file...")
        
        video_bytes = await video_file.download_as_bytearray()
        
        await status_msg.edit_text("🔧 Converting video to MP3...")
        
        audio = AudioSegment.from_file(BytesIO(video_bytes), format="mp4")
        audio.export(output_filename, format="mp3")
        
        await status_msg.edit_text("📤 Uploading MP3 file...")
        
        await update.message.reply_audio(
            audio=open(output_filename, 'rb'),
            caption="Here's your converted MP3 file!"
        )
        
        if os.path.exists(output_filename):
            os.remove(output_filename)
        
        await status_msg.delete()
            
    except Exception as e:
        logger.error(f"Error converting video: {e}")
        await update.message.reply_text("Sorry, I couldn't convert that video. Please try again.")

async def download_reel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download Instagram reel"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    if not context.args:
        await update.message.reply_text("Please send the Instagram reel URL after /reel command")
        return
    
    url = context.args[0]
    await save_user_link(user.id, url, "instagram_reel")
    
    if "instagram.com/reel/" not in url:
        await update.message.reply_text("Please provide a valid Instagram reel URL")
        return
    
    try:
        status_msg = await update.message.reply_text("🔍 Starting reel download...")
        
        shortcode = url.split("/reel/")[1].split("/")[0]
        
        await status_msg.edit_text("⬇️ Downloading reel from Instagram...")
        
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        unique_id = uuid4().hex
        filename = f"reel_{unique_id}.mp4"
        folder_name = f"reel_{unique_id}"
        
        L.download_post(post, target=folder_name)
        
        for file in os.listdir(folder_name):
            if file.endswith(".mp4"):
                os.rename(f"{folder_name}/{file}", filename)
                break
        
        await status_msg.edit_text("📤 Uploading reel to Telegram...")
        
        await update.message.reply_video(
            video=open(filename, 'rb'),
            caption="Here's your Instagram reel!"
        )
        
        if os.path.exists(filename):
            os.remove(filename)
        if os.path.exists(folder_name):
            for file in os.listdir(folder_name):
                os.remove(f"{folder_name}/{file}")
            os.rmdir(folder_name)
        
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Error downloading reel: {e}")
        await update.message.reply_text("Sorry, I couldn't download that reel. Please check the URL and try again.")

async def forward_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward videos to target channel"""
    if update.message.video:
        user = update.effective_user
        caption = f"From: @{user.username}\n{update.message.caption or ''}"
        
        try:
            await context.bot.send_video(
                chat_id=TARGET_CHANNEL,
                video=update.message.video.file_id,
                caption=caption
            )
        except Exception as e:
            logger.error(f"Error forwarding video: {e}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all bot users (admin only)"""
    user = update.effective_user
    if user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    if not user_data:
        await update.message.reply_text("No user data available yet.")
        return
    
    message = "📊 Bot Users:\n\n"
    for user_id, data in user_data.items():
        message += (
            f"👤 User ID: {user_id}\n"
            f"🆔 Username: @{data.get('username', 'N/A')}\n"
            f"📛 Name: {data.get('first_name', 'N/A')}\n"
            f"📅 First seen: {data['first_seen']}\n"
            f"🔄 Last interaction: {data['last_interaction']}\n"
            f"────────────────────\n"
        )
    
    for i in range(0, len(message), 4096):
        await update.message.reply_text(message[i:i+4096])

async def list_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all shared links (admin only)"""
    user = update.effective_user
    if user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    if not user_links:
        await update.message.reply_text("No links have been shared yet.")
        return
    
    message = "🔗 Shared Links:\n\n"
    for user_id, links in user_links.items():
        user_info = user_data.get(user_id, {})
        message += f"👤 User: @{user_info.get('username', 'N/A')} (ID: {user_id})\n"
        
        for link in links:
            message += (
                f"🔗 {link['type']}: {link['link']}\n"
                f"⏰ {link['timestamp']}\n"
                f"────────────────────\n"
            )
    
    for i in range(0, len(message), 4096):
        await update.message.reply_text(message[i:i+4096])

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast message to all users (admin only)"""
    user = update.effective_user
    if user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a message with /broadcast to forward it to all users.")
        return
    
    if not user_data:
        await update.message.reply_text("No users to broadcast to.")
        return
    
    total_users = len(user_data)
    success = 0
    failed = 0
    
    status_msg = await update.message.reply_text(f"📢 Broadcasting to {total_users} users... 0% complete")
    
    for i, (user_id, _) in enumerate(user_data.items()):
        try:
            await context.bot.copy_message(
                chat_id=int(user_id),
                from_chat_id=update.message.chat_id,
                message_id=update.message.reply_to_message.message_id
            )
            success += 1
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
            failed += 1
        
        if (i + 1) % max(1, total_users // 10) == 0 or (i + 1) == total_users:
            percent = int((i + 1) / total_users * 100)
            await status_msg.edit_text(
                f"📢 Broadcasting to {total_users} users... {percent}% complete\n"
                f"✅ Success: {success} | ❌ Failed: {failed}"
            )
    
    await status_msg.edit_text(
        f"📢 Broadcast completed!\n"
        f"✅ Success: {success} | ❌ Failed: {failed}"
    )

class TelegramBot:
    def __init__(self):
        self.application = None
        self.loop = None
        self.thread = None
        self.stop_event = threading.Event()
    
    async def initialize(self):
        """Initialize the bot application"""
        self.application = Application.builder().token(TOKEN).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", start))
        self.application.add_handler(CommandHandler("convert", convert_to_mp3))
        self.application.add_handler(CommandHandler("reel", download_reel))
        self.application.add_handler(CommandHandler("users", list_users, filters=filters.User(AUTHORIZED_USERS)))
        self.application.add_handler(CommandHandler("links", list_links, filters=filters.User(AUTHORIZED_USERS)))
        self.application.add_handler(CommandHandler("broadcast", broadcast, filters=filters.User(AUTHORIZED_USERS)))
        self.application.add_handler(MessageHandler(filters.VIDEO, forward_to_channel))
        
        # Start the bot
        await self.application.initialize()
        await self.application.start()
        
        # Keep running until stopped
        while not self.stop_event.is_set():
            await asyncio.sleep(1)
        
        # Clean up
        await self.application.stop()
        await self.application.shutdown()
    
    def run_bot(self):
        """Run the bot in a background thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self.initialize())
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            if self.loop:
                self.loop.close()
    
    def start(self):
        """Start the bot thread"""
        if self.thread and self.thread.is_alive():
            return
        
        self.thread = threading.Thread(target=self.run_bot, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop the bot"""
        self.stop_event.set()

# Streamlit app placeholder
def run_streamlit_app():
    """Minimal Streamlit app to keep the process running"""
    import streamlit as st
    st.title("Telegram Bot is Running")
    st.write("The bot is running in the background.")
    st.write("This page is just a placeholder to keep the process alive.")
    
    # Display bot status
    bot_status = st.empty()
    
    # Keep the app running
    while True:
        bot_status.write(f"Bot is running... Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(1)

if __name__ == '__main__':
    # Start the bot
    bot = TelegramBot()
    bot.start()
    
    # Start the Streamlit app (this will block)
    run_streamlit_app()
