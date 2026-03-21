# JobCraft — Setup Guide

A step-by-step guide to get JobCraft running on your laptop. No coding experience needed.

---

## What You Need Before Starting

Install these three things if you don't have them:

| Tool | Why | Download Link |
|------|-----|--------------|
| **Python 3.11+** | Runs the backend server | [python.org/downloads](https://www.python.org/downloads/) |
| **Node.js 18+** | Runs the frontend interface | [nodejs.org](https://nodejs.org/) (pick the LTS version) |
| **Git** | (Optional) Version control | [git-scm.com/downloads](https://git-scm.com/downloads) |

> **Tip:** During Python installation on Windows, check the box **"Add Python to PATH"**.

---

## Step 1: Get a FREE API Key (Google Gemini — no credit card)

JobCraft uses AI to tailor resumes. You can use **Google Gemini for free** (no payment needed):

1. Go to **[aistudio.google.com](https://aistudio.google.com)**
2. Sign in with your Google account
3. Click **"Get API key"** or **"Create API key"**
4. Create a new key and copy it — it starts with `AIza...`
5. Paste it in Step 3 (or in the app under Settings)

> **Free tier:** Generous daily limits (e.g. 1,500 requests/day for Gemini Flash). No credit card required.

> **Optional:** You can instead use a paid Anthropic Claude key from [console.anthropic.com](https://console.anthropic.com/) — paste it in the same API Key field; the app detects which key you use.

---

## Step 1B (Recommended): Use Ollama (FREE, local, no quotas)

If you want **unlimited AI usage without any API keys**, use **Ollama** (runs the AI model on your PC).

1. Install Ollama: [ollama.com](https://ollama.com/)
2. Open a terminal and run:

```
ollama pull llama3.1
ollama serve
```

3. In your `jobcraft/.env`, set:

```
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
```

---

## Step 2: Set Up the Project

Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and run:

### Windows Users
```
cd "c:\RAKESH\AI\SIDE HUSTLE\RESUMEENGINE\jobcraft"
```

### Create a Python virtual environment
```
python -m venv .venv
```

### Activate it
**Windows:**
```
.venv\Scripts\activate
```
**Mac/Linux:**
```
source .venv/bin/activate
```

### Install Python packages
```
pip install -r backend/requirements.txt
```

### Install Playwright browser (for job scraping)
```
playwright install chromium
```

### Install frontend packages
```
cd frontend
npm install
cd ..
```

---

## Step 3: Configure Your API Key

1. In the `jobcraft` folder, find the file `.env.example`
2. Copy it and rename the copy to `.env`
   - **Windows:** `copy .env.example .env`
   - **Mac/Linux:** `cp .env.example .env`
3. Open `.env` in any text editor (Notepad, VS Code, etc.)
4. Replace `AIza-your-free-key-here` with your **Gemini API key** from Step 1 (starts with `AIza...`)
5. Change the `SECRET_KEY` to any long random text (e.g., mash your keyboard)
6. Save the file

Your `.env` should look like:
```
GEMINI_API_KEY=AIzaSy...your-actual-gemini-key...
SECRET_KEY=my-super-secret-random-string-xyz789
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=jobcraft2024
```

---

## Step 4: Run the App

### Option A: One-Command Start (Recommended)

**Windows:** Double-click `run.bat` or type:
```
run.bat
```

**Mac/Linux:**
```
bash run.sh
```

### Option B: Manual Start (if the script doesn't work)

Open **two separate terminal windows**.

**Terminal 1 — Backend:**
```
cd backend
..\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8080 --reload
```

**Terminal 2 — Frontend:**
```
cd frontend
npm run dev
```

Then open your browser to: **http://localhost:5173**

---

## Step 5: First Login

1. Open **http://localhost:5173** in your browser
2. Log in with:
   - **Username:** `admin`
   - **Password:** `jobcraft2024`
3. **Important:** Go to Settings and change your password immediately!

---

## Step 6: Your First Job Search

1. After logging in, you'll see the **Upload** page
2. Drag & drop your resume (PDF or DOCX, max 5MB)
3. Add your target job titles (e.g., "Product Manager", "Software Engineer")
4. Add your preferred locations (e.g., "Hyderabad", "Remote")
5. Select which job portals to search
6. Click **Start Search**
7. Watch the agent work in real-time!
8. When done, browse your ranked results on the **Dashboard**

---

## Troubleshooting

### "Python is not recognized"
You need to add Python to your PATH. Reinstall Python and check **"Add Python to PATH"** during installation.

### "npm is not recognized"
Install Node.js from [nodejs.org](https://nodejs.org/). Restart your terminal after installing.

### "Module not found" errors in Python
Make sure your virtual environment is activated:
- Windows: `.venv\Scripts\activate`
- Mac/Linux: `source .venv/bin/activate`

### Scraping returns no jobs
Job portals sometimes block automated access. Try:
- Waiting 5 minutes and trying again
- Using a different portal (Indeed tends to be more accessible)
- Checking your internet connection

### "No API key" or "API key not configured"
1. Get a **free Gemini key** at [aistudio.google.com](https://aistudio.google.com) (no credit card)
2. Go to **Settings** in the app
3. Paste the key (starts with `AIza...`) in the API Key field
4. Click Save

### Port already in use
If port 8000 or 5173 is busy:
- **Windows:** `netstat -ano | findstr :8080` then `taskkill /PID <pid> /F`
- **Mac/Linux:** `lsof -i :8080` then `kill -9 <pid>`

### Database errors
Delete the database and restart:
- Delete `data/jobcraft.db`
- Restart the backend

---

## Stopping the App

- **If you used run.bat/run.sh:** Press `Ctrl+C` in the terminal
- **If you started manually:** Press `Ctrl+C` in both terminal windows
- **Windows run.bat:** Close all three command prompt windows

---

## Updating

If you pull new code, re-install dependencies:
```
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```
