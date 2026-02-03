# 🎬 TikTok Downloader Bot Service

A production-ready Telegram bot for downloading TikTok videos without watermark, with a beautiful web dashboard and analytics.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram)
![Supabase](https://img.shields.io/badge/Supabase-Database-3ECF8E?logo=supabase)
![Render](https://img.shields.io/badge/Render-Deployed-46E3B7?logo=render)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **Telegram Bot** | Easy-to-use bot interface |
| 📊 **Web Dashboard** | Live stats with beautiful UI |
| 🏥 **Health Endpoint** | `/health` for uptime monitoring |
| 📈 **Analytics** | Track users and downloads |
| 🗄️ **Supabase** | Persistent data storage |
| 🚀 **Render Ready** | One-click deployment |

---

## 📁 Project Structure

```
tiktok-bot-service/
├── app.py              # Main FastAPI + Telegram bot
├── database.py         # Supabase integration
├── downloader.py       # TikTok downloader logic
├── requirements.txt    # Python dependencies
├── render.yaml         # Render deployment config
├── supabase_schema.sql # Database schema
├── .env.example        # Environment template
└── .gitignore
```

---

## 🚀 Deployment Guide

### Step 1: Create Telegram Bot

1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the **Bot Token**

### Step 2: Setup Supabase

1. Go to [supabase.com](https://supabase.com) and create a project
2. Open the **SQL Editor**
3. Run the contents of `supabase_schema.sql`
4. Go to **Settings > API** and copy:
   - Project URL
   - anon/public API key

### Step 3: Deploy to Render

1. Push this folder to a GitHub repository
2. Go to [render.com](https://render.com)
3. Click **New > Web Service**
4. Connect your GitHub repo
5. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`

### Step 4: Set Environment Variables

In Render dashboard, add these environment variables:

| Variable | Value |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `SUPABASE_URL` | `https://your-project.supabase.co` |
| `SUPABASE_KEY` | Your Supabase anon key |
| `WEBHOOK_URL` | `https://your-app.onrender.com` |

### Step 5: Setup Cronjob (Keep Alive)

Free Render services sleep after 15 minutes of inactivity. Use a cronjob to keep it alive:

1. Go to [cron-job.org](https://cron-job.org) (free)
2. Create a new cronjob:
   - URL: `https://your-app.onrender.com/health`
   - Schedule: Every 14 minutes
   - Method: GET

---

## 🔗 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard with statistics |
| `/health` | GET | Health check for uptime monitoring |
| `/webhook` | POST | Telegram webhook handler |
| `/api/stats` | GET | JSON statistics endpoint |

---

## 🤖 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/help` | Show help message |
| `/stats` | View download statistics |

**Usage:** Just send a TikTok video link to download!

---

## 📊 Dashboard Preview

The web dashboard shows:
- 👥 Total Users
- 📥 Total Downloads
- ✅ Successful Downloads
- 📅 Today's Downloads

Auto-refreshes every 30 seconds.

---

## 🛠️ Local Development

```bash
# Clone the repo
git clone https://github.com/yourusername/tiktok-bot-service.git
cd tiktok-bot-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your values

# Run locally
uvicorn app:app --reload --port 8000
```

For local Telegram testing, use [ngrok](https://ngrok.com):
```bash
ngrok http 8000
# Use the ngrok URL as WEBHOOK_URL
```

---

## 📝 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `SUPABASE_URL` | No* | Supabase project URL |
| `SUPABASE_KEY` | No* | Supabase anon key |
| `WEBHOOK_URL` | Yes | Your app's public URL |
| `PORT` | No | Port (auto-set by Render) |

*If not set, uses in-memory storage (data lost on restart)

---

## 🔒 Security

- No sensitive data stored
- Downloads are temporary (deleted after sending)
- Uses Supabase Row Level Security
- HTTPS enforced on Render

---

## 📜 License

MIT License - Free to use and modify!

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

<p align="center">
  <strong>Made with ❤️ by devtint</strong>
</p>
