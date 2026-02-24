# AI Ad Creator

Fully automated Facebook video ad creation via a Telegram bot.

**Message the bot:** `Create 5 ads for usaemployeeadvocates.com`

The system then automatically:
1. Researches your website + web searches for context
2. Writes N distinct ad scripts (different angles/hooks)
3. Generates AI avatar videos via HeyGen
4. Downloads relevant B-roll from Pexels
5. Edits everything together with subtitles + disclaimer
6. Uploads to Google Drive
7. Logs all links to Google Sheets
8. Sends you the links via Telegram

---

## Requirements

- Python 3.11+
- FFmpeg (for video editing)
- The API keys listed below

---

## Quick Start

### 1. Install FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### 2. Install Python dependencies

```bash
cd ai-ad-creator
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set up API Keys

Run the interactive setup wizard:
```bash
python main.py --setup
```

Or manually copy `.env.example` → `.env` and fill in all keys.

### 4. Set up Google Credentials (Required for Drive + Sheets)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable these APIs:
   - Google Drive API
   - Google Sheets API
4. Go to **Credentials** → **Create Credentials** → **Service Account**
5. Name it `ai-ad-creator`, click Create
6. Click on the service account → **Keys** tab → **Add Key** → **JSON**
7. Save the downloaded JSON as `google_credentials.json` in this project folder
8. **Share your Google Drive folder** with the service account email (ends in `@...iam.gserviceaccount.com`) — give it "Editor" access
9. **Share your Google Sheet** with the same service account email — give it "Editor" access

### 5. Get your API Keys

| Service | Where to get it | Cost |
|---------|----------------|------|
| **Telegram Bot Token** | Message @BotFather → `/newbot` | Free |
| **Anthropic (Claude)** | [console.anthropic.com](https://console.anthropic.com) | Pay per use |
| **OpenAI (Whisper)** | [platform.openai.com](https://platform.openai.com) | ~$0.006/min |
| **HeyGen** | [app.heygen.com/settings](https://app.heygen.com/settings) → API | ~$0.10/credit |
| **Pexels** | [pexels.com/api](https://www.pexels.com/api/) | Free |
| **Tavily** | [tavily.com](https://tavily.com) | Free tier available |

### 6. Configure your Google IDs

- **Drive Folder ID**: Open your Google Drive folder → the URL contains `/folders/YOUR_FOLDER_ID`
- **Sheet ID**: Open your Google Sheet → URL contains `/spreadsheets/d/YOUR_SHEET_ID/`

Add both to your `.env` file.

### 7. Start the bot

```bash
python main.py
```

---

## Usage

Message your Telegram bot:

```
Create 5 ads for usaemployeeadvocates.com
Make 3 talking head ads for mysite.com
Generate 2 full broll ads for example.com
```

**Ad Types:**
- `full broll` (default) — Avatar takes up the full vertical frame; B-roll is overlaid during key moments
- `talking head` — Avatar is placed at the bottom with B-roll filling the background (like a split-screen)

**Bot Commands:**
- `/start` — Welcome message
- `/avatars` — List your available HeyGen avatars
- `/status` — Show running jobs
- `/help` — Help

---

## Architecture

```
Telegram Message
      │
      ▼
┌─────────────────────┐
│   Orchestrator      │  Coordinates all agents
└─────────┬───────────┘
          │
     ┌────┴────┐
     ▼         ▼
┌─────────┐  ┌───────────────┐
│Research │  │ Script Writer  │ (Claude)
│ Agent   │  │   (Claude)    │
└─────────┘  └───────┬───────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌─────────────┐  ┌────────┐  ┌───────────┐
│   HeyGen    │  │ Pexels │  │  (parallel)│
│Avatar Video │  │ B-roll │  │           │
└──────┬──────┘  └───┬────┘  └───────────┘
       │             │
       └──────┬──────┘
              ▼
     ┌────────────────┐
     │  Video Editor  │  FFmpeg: overlay, subtitles, disclaimer
     │  (FFmpeg +     │
     │   Whisper)     │
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │ Quality Checker│
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │    Uploader    │  Google Drive + Sheets
     └───────┬────────┘
             │
             ▼
     Telegram: Drive links sent back
```

---

## Cost Estimate (per 5 ads, ~45s each)

| Service | Usage | Estimated Cost |
|---------|-------|---------------|
| HeyGen | 5 × ~45s videos | ~$5–15 (depends on plan) |
| Claude (Anthropic) | Research + 5 scripts | ~$0.30 |
| OpenAI Whisper | 5 × ~45s audio | ~$0.02 |
| Pexels | 15 B-roll clips | Free |
| Tavily | 3 searches | Free (within free tier) |
| **Total** | | **~$5–15 per 5 ads** |

---

## Customization

### Change the disclaimer text
Edit `DISCLAIMER_TEXT` in `config.py`.

### Use a specific HeyGen avatar
1. Run `/avatars` in the Telegram bot to see available IDs
2. Add `HEYGEN_DEFAULT_AVATAR_ID=your_id` to `.env`

### Adjust video dimensions
The default is 1080×1920 (9:16 portrait for Facebook/Instagram).
Change `VIDEO_WIDTH` and `VIDEO_HEIGHT` in `.env`.

### Change the ad script style
Edit the `AD_STRUCTURE_GUIDE` and `_build_script_prompt` in `agents/script_writer.py`.

---

## Troubleshooting

**"HeyGen API error"** — Check your API key and account credits at app.heygen.com

**"No subtitles generated"** — Check your OpenAI API key and account balance

**"Google credentials not found"** — Make sure `google_credentials.json` is in the project folder

**"FFmpeg not found"** — Install FFmpeg and ensure it's on your system PATH

**Videos have no B-roll** — Check your Pexels API key; also verify the key is set in `.env`
