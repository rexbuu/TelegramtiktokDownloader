"""
SSSTIK TikTok Downloader - Telegram Bot & API Service
======================================================

Features:
- Telegram bot for easy downloads (supports both webhook and polling mode)
- Web dashboard with stats
- /health endpoint for uptime monitoring
- Supabase integration for analytics

Deploy on Render.com or run locally
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from downloader import SsstikDownloader
from database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Initialize components
db = Database(SUPABASE_URL, SUPABASE_KEY)
downloader = SsstikDownloader()
telegram_app = None

# Queue system for downloads (1 at a time)
download_queue = asyncio.Queue()
is_processing = False

# Cooldown tracking (user_id -> last_download_time)
user_cooldowns: dict[int, datetime] = {}
COOLDOWN_SECONDS = 15


async def download_worker():
    """Background worker that processes downloads one at a time"""
    global is_processing
    
    while True:
        try:
            # Get next item from queue
            task = await download_queue.get()
            is_processing = True
            
            user_id = task['user_id']
            message_text = task['url']
            update = task['update']
            processing_msg = task['processing_msg']
            queue_position = task.get('queue_position', 0)
            
            try:
                # Update message to show processing
                try:
                    await processing_msg.edit_text("⏳ Downloading your video...")
                except:
                    pass
                
                # Download the video
                result = await downloader.download_video(message_text)
                
                if result['success']:
                    # Track successful download
                    await db.track_download(user_id, message_text, True)
                    
                    # Send the video file
                    with open(result['download_path'], 'rb') as video_file:
                        await update.message.reply_video(
                            video=video_file,
                            caption="✅ Here's your video without watermark!\n\n🤖 Powered by @BadCodeWriter"
                        )
                    
                    # Clean up the file
                    os.remove(result['download_path'])
                    
                    try:
                        await processing_msg.delete()
                    except:
                        pass
                else:
                    # Track failed download
                    await db.track_download(user_id, message_text, False)
                    
                    try:
                        await processing_msg.edit_text(
                            f"❌ Failed to download video.\n\n"
                            f"Error: {result.get('error', 'Unknown error')}\n\n"
                            f"Please try again or check if the link is correct."
                        )
                    except:
                        pass
            
            except Exception as e:
                logger.error(f"Error processing video: {e}")
                await db.track_download(user_id, message_text, False)
                try:
                    await processing_msg.edit_text(
                        "❌ An error occurred. Please try again later."
                    )
                except:
                    pass
            
            finally:
                download_queue.task_done()
                is_processing = False
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
            is_processing = False


# ============== Telegram Bot Handlers ==============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    # Track user
    await db.track_user(user.id, user.username or user.first_name)
    
    welcome_message = f"""
🎬 **TikTok Video Downloader Bot**

Hi {user.first_name}! 👋

Send me a TikTok video link and I'll download it for you without watermark!

**How to use:**
1. Copy a TikTok video link
2. Paste it here
3. Get your video!

**Supported links:**
• `https://www.tiktok.com/@user/video/...`
• `https://vm.tiktok.com/...`

📊 /stats - View your download stats
❓ /help - Show this message

⏱️ Note: 15 second cooldown between downloads
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await start_command(update, context)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command - shows user's personal stats only"""
    user = update.effective_user
    
    # Get user's personal stats
    user_stats = await db.get_user_stats(user.id)
    
    stats_message = f"""
📊 **Your Download Statistics**

📥 Total Downloads: **{user_stats['total_downloads']:,}**
✅ Successful: **{user_stats['successful_downloads']:,}**
❌ Failed: **{user_stats['failed_downloads']:,}**

📅 Today: **{user_stats['today_downloads']:,}**

🕐 Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    """
    await update.message.reply_text(stats_message, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle TikTok URL messages"""
    user = update.effective_user
    message_text = update.message.text.strip()
    
    # Check if it's a TikTok URL
    if 'tiktok.com' not in message_text.lower():
        await update.message.reply_text(
            "❌ Please send a valid TikTok video link.\n\n"
            "Example: `https://www.tiktok.com/@user/video/123456789`",
            parse_mode='Markdown'
        )
        return
    
    # Check cooldown
    now = datetime.now(timezone.utc)
    if user.id in user_cooldowns:
        last_download = user_cooldowns[user.id]
        elapsed = (now - last_download).total_seconds()
        remaining = COOLDOWN_SECONDS - elapsed
        
        if remaining > 0:
            await update.message.reply_text(
                f"⏱️ Please wait **{int(remaining)}** seconds before downloading again.",
                parse_mode='Markdown'
            )
            return
    
    # Update cooldown
    user_cooldowns[user.id] = now
    
    # Check queue size
    queue_size = download_queue.qsize()
    
    if queue_size > 0:
        processing_msg = await update.message.reply_text(
            f"⏳ Added to queue. Position: **{queue_size + 1}**\n"
            f"Please wait...",
            parse_mode='Markdown'
        )
    else:
        processing_msg = await update.message.reply_text("⏳ Processing your video...")
    
    # Add to queue
    await download_queue.put({
        'user_id': user.id,
        'url': message_text,
        'update': update,
        'processing_msg': processing_msg,
        'queue_position': queue_size + 1
    })


# ============== FastAPI App ==============

# Track the worker task
worker_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global telegram_app, worker_task
    
    # Startup
    logger.info("Starting up...")
    logger.info(f"Telegram Bot: {'Configured' if TELEGRAM_BOT_TOKEN else 'Not configured'}")
    logger.info(f"Supabase: {'Configured' if SUPABASE_URL else 'Using in-memory storage'}")
    
    # Initialize database
    await db.initialize()
    
    # Start the download worker
    worker_task = asyncio.create_task(download_worker())
    logger.info("Download queue worker started")
    
    # Setup Telegram bot
    if TELEGRAM_BOT_TOKEN:
        telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("stats", stats_command))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await telegram_app.initialize()
        
        # Start polling mode
        logger.info("Starting bot in polling mode...")
        await telegram_app.start()
        asyncio.create_task(telegram_app.updater.start_polling(drop_pending_updates=True))
    else:
        logger.warning("No TELEGRAM_BOT_TOKEN set - bot functionality disabled")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    
    # Stop worker
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    
    if telegram_app:
        if telegram_app.updater.running:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


app = FastAPI(
    title="TikTok Downloader Bot",
    description="Telegram bot for downloading TikTok videos",
    version="1.0.0",
    lifespan=lifespan
)


# ============== API Endpoints ==============

@app.get("/health")
async def health_check():
    """Health check endpoint for uptime monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "tiktok-downloader-bot"
    }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle Telegram webhook updates"""
    if telegram_app:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    return {"ok": True}


@app.get("/api/stats")
async def get_stats():
    """Get download statistics as JSON"""
    stats = await db.get_stats()
    return JSONResponse(stats)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Web dashboard with statistics"""
    stats = await db.get_stats()
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TikTok Downloader Bot - Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0f0f1a;
            --bg-secondary: #1a1a2e;
            --bg-card: rgba(255, 255, 255, 0.05);
            --text-primary: #ffffff;
            --text-secondary: #a0a0b0;
            --accent: #00d4ff;
            --accent-secondary: #7b2cbf;
            --success: #00ff88;
            --danger: #ff4757;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
            min-height: 100vh;
            color: var(--text-primary);
            padding: 2rem;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 3rem;
        }}
        
        h1 {{
            font-size: 2.5rem;
            background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        
        .subtitle {{
            color: var(--text-secondary);
            font-size: 1.1rem;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }}
        
        .stat-card {{
            background: var(--bg-card);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 2rem;
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 40px rgba(0, 212, 255, 0.2);
        }}
        
        .stat-icon {{
            font-size: 2.5rem;
            margin-bottom: 1rem;
        }}
        
        .stat-value {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}
        
        .stat-value.users {{
            color: var(--accent);
        }}
        
        .stat-value.downloads {{
            color: var(--success);
        }}
        
        .stat-value.failed {{
            color: var(--danger);
        }}
        
        .stat-value.today {{
            color: var(--accent-secondary);
        }}
        
        .stat-label {{
            color: var(--text-secondary);
            font-size: 1rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .cta-section {{
            text-align: center;
            padding: 3rem;
            background: var(--bg-card);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .cta-section h2 {{
            margin-bottom: 1rem;
        }}
        
        .cta-section p {{
            color: var(--text-secondary);
            margin-bottom: 2rem;
        }}
        
        .telegram-btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: linear-gradient(90deg, #0088cc, #00aaff);
            color: white;
            text-decoration: none;
            padding: 1rem 2rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 1.1rem;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .telegram-btn:hover {{
            transform: scale(1.05);
            box-shadow: 0 10px 30px rgba(0, 136, 204, 0.4);
        }}
        
        footer {{
            text-align: center;
            margin-top: 3rem;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        
        .live-indicator {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--success);
            font-size: 0.9rem;
            margin-top: 1rem;
        }}
        
        .live-dot {{
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎬 TikTok Downloader Bot</h1>
            <p class="subtitle">Download TikTok videos without watermark via Telegram</p>
            <div class="live-indicator">
                <span class="live-dot"></span>
                Service Online
            </div>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">👥</div>
                <div class="stat-value users">{stats['total_users']:,}</div>
                <div class="stat-label">Total Users</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">📥</div>
                <div class="stat-value downloads">{stats['total_downloads']:,}</div>
                <div class="stat-label">Total Downloads</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">✅</div>
                <div class="stat-value downloads">{stats['successful_downloads']:,}</div>
                <div class="stat-label">Successful</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">📅</div>
                <div class="stat-value today">{stats['today_downloads']:,}</div>
                <div class="stat-label">Today's Downloads</div>
            </div>
        </div>
        
        <div class="cta-section">
            <h2>Start Downloading Now!</h2>
            <p>Open our Telegram bot and paste any TikTok video link to get started.</p>
            <a href="https://t.me/tiktokvideodownload_robot" class="telegram-btn">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.161c-.18 1.897-.962 6.502-1.359 8.627-.168.9-.5 1.201-.82 1.23-.697.064-1.226-.461-1.901-.903-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.139-5.062 3.345-.479.329-.913.489-1.302.481-.428-.009-1.252-.242-1.865-.44-.751-.245-1.349-.374-1.297-.789.027-.216.324-.437.893-.663 3.498-1.524 5.831-2.529 6.998-3.015 3.333-1.386 4.025-1.627 4.477-1.635.099-.002.321.023.465.141a.506.506 0 01.171.325c.016.093.036.306.02.472z"/>
                </svg>
                Open in Telegram
            </a>
        </div>
        
        <footer>
            <p>Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p style="margin-top: 0.5rem;">Powered by FastAPI • Hosted on Render</p>
        </footer>
    </div>
    
    <script>
        // Auto-refresh stats every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
