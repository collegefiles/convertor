import os
import json
import logging
from uuid import uuid4
from datetime import datetime
from pydub import AudioSegment
from io import BytesIO
import instaloader
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Configuration
TOKEN = "7769945024:AAFJQDHv0HhaheienRwNqcYDUMwIMxpAjo8"
CHANNEL_ID = "-1002114707908"  # Replace with your channel ID
AUTHORIZED_USER_ID = 6897230899  # Replace with your user ID

# Initialize Instaloader
L = instaloader.Instaloader()

# File storage
USER_DATA_FILE = "user_data.json"

# Load existing data
try:
    with open(USER_DATA_FILE, "r") as f:
        user_data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    user_data = {}

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def save_user_data(user_id: int, username: str = None, first_name: str = None):
    """Save user interaction data"""
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {
            "first_seen": datetime.now().isoformat(),
            "username": username,
            "first_name": first_name,
            "last_interaction": datetime.now().isoformat()
        }
    else:
        user_data[user_id]["last_interaction"] = datetime.now().isoformat()
    
    with open(USER_DATA_FILE, "w") as f:
        json.dump(user_data, f, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    await update.message.reply_text(
        "Hello! I'm your media bot. I can:\n"
        "1. Convert videos to MP3 - reply to a video with /convert\n"
        "2. Download Instagram reels - send /reel URL"
    )

async def convert_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Video to MP3 conversion"""
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Please reply to a video with /convert")
        return
    
    try:
        video_file = await update.message.reply_to_message.video.get_file()
        video_bytes = await video_file.download_as_bytearray()
        
        audio = AudioSegment.from_file(BytesIO(video_bytes), format="mp4")
        output = BytesIO()
        audio.export(output, format="mp3")
        output.seek(0)
        
        await update.message.reply_audio(
            audio=InputFile(output, filename="converted.mp3"),
            caption="Here's your MP3 file!"
        )
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await update.message.reply_text("Conversion failed. Please try again.")

async def download_reel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instagram reel downloader"""
    if not context.args:
        await update.message.reply_text("Please send /reel <URL>")
        return
    
    url = context.args[0]
    if "instagram.com/reel/" not in url:
        await update.message.reply_text("Invalid Instagram reel URL")
        return
    
    try:
        shortcode = url.split("/reel/")[1].split("/")[0]
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Download reel
        unique_id = uuid4().hex
        filename = f"reel_{unique_id}.mp4"
        L.download_post(post, target=unique_id)
        
        # Find downloaded file
        for file in os.listdir(unique_id):
            if file.endswith(".mp4"):
                with open(f"{unique_id}/{file}", "rb") as video_file:
                    await update.message.reply_video(
                        video=InputFile(video_file),
                        caption="Here's your Instagram reel!"
                    )
                break
        
        # Cleanup
        for f in os.listdir(unique_id):
            os.remove(f"{unique_id}/{f}")
        os.rmdir(unique_id)
    except Exception as e:
        logger.error(f"Reel download error: {e}")
        await update.message.reply_text("Failed to download reel. Please try again.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users"""
    user = update.effective_user
    if user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to broadcast")
        return
    
    success = 0
    failures = 0
    
    for user_id in user_data:
        try:
            await context.bot.forward_message(
                chat_id=int(user_id),
                from_chat_id=update.message.chat_id,
                message_id=update.message.reply_to_message.message_id
            )
            success += 1
        except Exception as e:
            logger.error(f"Broadcast failed to {user_id}: {e}")
            failures += 1
    
    await update.message.reply_text(
        f"Broadcast complete!\n"
        f"✅ Success: {success}\n"
        f"❌ Failures: {failures}"
    )

async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all file types"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    message = update.message
    if message.document:
        file = message.document
    elif message.video:
        file = message.video
    elif message.audio:
        file = message.audio
    elif message.photo:
        file = message.photo[-1]
    else:
        return
    
    try:
        # Forward to channel
        await message.forward(chat_id=CHANNEL_ID)
        
        # Get direct download link
        file_obj = await file.get_file()
        await message.reply_text(
            f"File available at:\n{file_obj.file_path}\n"
            f"Direct download: https://api.telegram.org/file/bot{TOKEN}/{file_obj.file_path}"
        )
    except Exception as e:
        logger.error(f"File handling error: {e}")
        await message.reply_text("Failed to process file")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all bot users"""
    user = update.effective_user
    if user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized")
        return
    
    if not user_data:
        await update.message.reply_text("No users yet")
        return
    
    msg = "📊 Bot Users:\n\n"
    for uid, data in user_data.items():
        msg += (
            f"👤 ID: {uid}\n"
            f"🆔 Username: @{data.get('username', 'N/A')}\n"
            f"📅 Last Active: {data['last_interaction']}\n"
            "────────────────────\n"
        )
    
    await update.message.reply_text(msg[:4000])  # Truncate if too long

def main():
    """Initialize and run the bot"""
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("convert", convert_to_mp3))
    application.add_handler(CommandHandler("reel", download_reel))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("users", list_users))
    
    # File handlers
    application.add_handler(MessageHandler(
        filters.Document.VIDEO | filters.Document.AUDIO | 
        filters.VIDEO | filters.PHOTO | filters.AUDIO,
        handle_files
    ))
    
    # Run with polling (REQUIRED - cannot be removed)
    application.run_polling()

if __name__ == "__main__":
    main()
