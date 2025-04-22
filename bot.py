import os
import logging
import asyncio
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from pydub import AudioSegment
from io import BytesIO
import instaloader
from uuid import uuid4
from datetime import datetime

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram Bot Token
TOKEN = "7769945024:AAFJQDHv0HhaheienRwNqcYDUMwIMxpAjo8"

# Initialize Instaloader
L = instaloader.Instaloader()

# Authorized users (add your Telegram user ID)
AUTHORIZED_USERS = [6897230899]  # Replace with your actual user ID

# File to store user data
USER_DATA_FILE = "user_data.json"

# Load existing user data
try:
    with open(USER_DATA_FILE, "r") as f:
        user_data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    user_data = {}

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message and save user data"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    await update.message.reply_text(
        "Hi! I'm your media bot. I can:\n"
        "1. Convert videos to MP3 - reply to a video with /convert\n"
        "2. Download Instagram reels - send /reel <URL>"
    )

async def convert_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert video to MP3 using pydub with progress updates"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Please reply to a video file with /convert")
        return
    
    try:
        # Get the video file
        video_file = await update.message.reply_to_message.video.get_file()
        unique_id = uuid4().hex
        output_filename = f"converted_{unique_id}.mp3"
        
        # Inform user we're starting
        status_msg = await update.message.reply_text("⬇️ Downloading video file...")
        
        # Download the video to memory
        video_bytes = await video_file.download_as_bytearray()
        
        # Update status
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id,
            text="🔧 Converting video to MP3 (this may take a while for large files)..."
        )
        
        # Convert to MP3 using pydub
        audio = AudioSegment.from_file(BytesIO(video_bytes), format="mp4")
        
        # Estimate duration for progress
        duration_sec = len(audio) / 1000  # pydub works in milliseconds
        if duration_sec > 30:  # Only show progress for longer files
            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=status_msg.message_id,
                text=f"🔧 Converting: 0% (0/{int(duration_sec)} sec)"
            )
            
            # Simulate progress
            for i in range(1, 6):
                await asyncio.sleep(duration_sec/5)
                percent = i * 20
                await context.bot.edit_message_text(
                    chat_id=update.message.chat_id,
                    message_id=status_msg.message_id,
                    text=f"🔧 Converting: {percent}% ({int(duration_sec*i/5)}/{int(duration_sec)} sec)"
                )
        
        # Export the file
        audio.export(output_filename, format="mp3")
        
        # Update status
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id,
            text="📤 Uploading MP3 file..."
        )
        
        # Send the MP3 file
        await update.message.reply_audio(
            audio=open(output_filename, 'rb'),
            caption="Here's your converted MP3 file!"
        )
        
        # Clean up
        if os.path.exists(output_filename):
            os.remove(output_filename)
        
        # Delete status message
        await context.bot.delete_message(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id
        )
            
    except Exception as e:
        logger.error(f"Error converting video: {e}")
        await update.message.reply_text("Sorry, I couldn't convert that video. Please try again.")
        if 'status_msg' in locals():
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id,
                    message_id=status_msg.message_id
                )
            except:
                pass

async def download_reel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download Instagram reel with progress updates"""
    user = update.effective_user
    await save_user_data(user.id, user.username, user.first_name)
    
    if not context.args:
        await update.message.reply_text("Please send the Instagram reel URL after /reel command")
        return
    
    url = context.args[0]
    if "instagram.com/reel/" not in url:
        await update.message.reply_text("Please provide a valid Instagram reel URL")
        return
    
    try:
        # Status message
        status_msg = await update.message.reply_text("🔍 Starting reel download...")
        
        # Extract shortcode from URL
        shortcode = url.split("/reel/")[1].split("/")[0]
        
        # Update status
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id,
            text="⬇️ Downloading reel from Instagram..."
        )
        
        # Download the reel
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        unique_id = uuid4().hex
        filename = f"reel_{unique_id}.mp4"
        folder_name = f"reel_{unique_id}"
        
        # Simulate progress updates
        for i in range(1, 6):
            await asyncio.sleep(1)  # Simulate progress steps
            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=status_msg.message_id,
                text=f"⬇️ Downloading reel... {i*20}% complete"
            )
        
        L.download_post(post, target=folder_name)
        
        # Find the downloaded video file
        for file in os.listdir(folder_name):
            if file.endswith(".mp4"):
                os.rename(f"{folder_name}/{file}", filename)
                break
        
        # Update status
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id,
            text="📤 Uploading reel to Telegram..."
        )
        
        # Send the video file
        await update.message.reply_video(
            video=open(filename, 'rb'),
            caption="Here's your Instagram reel!"
        )
        
        # Clean up
        if os.path.exists(filename):
            os.remove(filename)
        if os.path.exists(folder_name):
            for file in os.listdir(folder_name):
                os.remove(f"{folder_name}/{file}")
            os.rmdir(folder_name)
        
        # Delete status message
        await context.bot.delete_message(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id
        )
        
    except Exception as e:
        logger.error(f"Error downloading reel: {e}")
        await update.message.reply_text("Sorry, I couldn't download that reel. Please check the URL and try again.")
        if 'status_msg' in locals():
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id,
                    message_id=status_msg.message_id
                )
            except:
                pass

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all users who interacted with the bot (admin only)"""
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
    
    # Split long messages to avoid Telegram limits
    for i in range(0, len(message), 4096):
        await update.message.reply_text(message[i:i+4096])

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast a message to all users (admin only)"""
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
            await context.bot.forward_message(
                chat_id=int(user_id),
                from_chat_id=update.message.chat_id,
                message_id=update.message.reply_to_message.message_id
            )
            success += 1
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
            failed += 1
        
        # Update progress every 10% or for last user
        if (i + 1) % max(1, total_users // 10) == 0 or (i + 1) == total_users:
            percent = int((i + 1) / total_users * 100)
            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=status_msg.message_id,
                text=f"📢 Broadcasting to {total_users} users... {percent}% complete\n"
                     f"✅ Success: {success} | ❌ Failed: {failed}"
            )
    
    await context.bot.edit_message_text(
        chat_id=update.message.chat_id,
        message_id=status_msg.message_id,
        text=f"📢 Broadcast completed!\n"
             f"✅ Success: {success} | ❌ Failed: {failed}"
    )

def main() -> None:
    """Start the bot."""
    if TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("ERROR: You need to set your Telegram bot token!")
        print("Get one from @BotFather and replace in the code")
        return
    
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("convert", convert_to_mp3))
    application.add_handler(CommandHandler("reel", download_reel))
    application.add_handler(CommandHandler("users", list_users, filters=filters.User(AUTHORIZED_USERS)))
    application.add_handler(CommandHandler("broadcast", broadcast, filters=filters.User(AUTHORIZED_USERS)))

    # Run the bot
    print("Bot is running... Press Ctrl+C to stop")
    application.run_polling()

if __name__ == '__main__':
    main()
