# AI Accident Detection & Emergency Response System — Deployment Guide

## System Overview
- **Backend**: Flask (Python) — detection engine, REST API, database, alerts
- **Frontend**: Static HTML/CSS/JS served by Flask
- **Models**: YOLOv8 (local `.pt` file) + Roboflow crash-detection API
- **Database**: SQLite (persisted on disk)
- **Alerts**: Telegram Bot, Email (SMTP), SMS/WhatsApp (Twilio)
- **Reports**: PDF generation via ReportLab

---

## 1. Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.10+ |
| Node.js | Not required (vanilla frontend) |
| Disk Space | ~2GB for models + dependencies + persistent data |
| RAM | Minimum 2GB (4GB+ recommended for YOLO + Roboflow inference) |
| Port | 5000 (configurable via `PORT` env var) |

---

## 2. Local Deployment (Development / Testing)

### 2.1 Clone & Install
```bash
git clone <your-repo-url>
cd "new python project"
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2.2 Environment Variables
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```
Edit `.env`:
```env
SECRET_KEY=your_random_flask_secret_key
PORT=5000
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
ROBOFLOW_API_KEY=your_roboflow_api_key
ROBOFLOW_WORKSPACE=your_roboflow_workspace
ROBOFLOW_PROJECT=your_roboflow_project
ROBOFLOW_VERSION=1
CONFIDENCE=0.5
PROCESS_EVERY_N_FRAMES=2
CRASH_CONFIDENCE_THRESHOLD=0.5
CAMERA_LOCATION=Unknown

# Optional: Email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
FROM_EMAIL=your_email@gmail.com

# Optional: SMS/WhatsApp via Twilio
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_FROM_PHONE=+1234567890
TWILIO_FROM_WHATSAPP=whatsapp:+1234567890
```

### 2.3 Run
```bash
python app.py
# OR for production locally:
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 2 --timeout 300 app:app
```

### 2.4 Access
- Dashboard: `http://localhost:5000`
- API: `http://localhost:5000/api/...`
- Default login: `admin` / `Dhiren@9974`

---

## 3. Render Deployment (Recommended — Already Configured)

This project includes a ready-to-use `render.yaml` and `Dockerfile`.

### 3.1 Steps
1. Push code to GitHub/GitLab
2. Go to [render.com](https://render.com) → **New** → **Web Service**
3. Connect your repository
4. Render auto-detects `render.yaml` and uses Docker runtime
5. Set the following **sync: false** environment variables in the Render dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ROBOFLOW_API_KEY`
   - `ROBOFLOW_WORKSPACE`
   - `ROBOFLOW_PROJECT`
   - `SECRET_KEY` (generate a random value)
   - `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL` (if using email)
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_PHONE`, `TWILIO_FROM_WHATSAPP` (if using SMS/WhatsApp)
6. Deploy

### 3.2 Render Configuration Details
| Setting | Value |
|---|---|
| Runtime | Docker |
| Plan | Starter ($7/mo) or higher recommended |
| Disk | 1GB mounted at `/app/data` for DB, frames, videos |
| Port | Dynamic via `PORT` env var |
| Health Check | `/api/status` |

### 3.3 Notes
- The `/app/data` disk preserves SQLite DB, accident frames, and output videos across deployments
- Cold starts may take 30-60s on the Starter plan
- For 24/7 operation, use the Standard plan or set up a ping service

---

## 4. Railway.app Deployment

### 4.1 Steps
1. Push code to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
3. Select your repo
4. Railway auto-detects Python and uses `Dockerfile` if present, or `requirements.txt`
5. Add environment variables (same as above)
6. Add a **Volume**:
   - Mount path: `/app/data`
   - Size: 1GB+

### 4.2 railway.json (Optional)
Create `railway.json` for explicit config:
```json
{
  "deploy": {
    "startCommand": "gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 300 app:app",
    "healthcheckPath": "/api/status"
  }
}
```

---

## 5. Fly.io Deployment

### 5.1 Steps
1. Install Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. `fly auth login`
3. `fly launch` (creates `fly.toml`)
4. Create a volume: `fly volumes create accident_data --size 1`
5. Update `fly.toml`:
```toml
[env]
  PORT = "5000"
  DATA_DIR = "/data"
  SECRET_KEY = "your_secret_key"

[mounts]
  source = "accident_data"
  destination = "/data"
```
6. Set secrets:
```bash
fly secrets set TELEGRAM_BOT_TOKEN=... ROBOFLOW_API_KEY=... SECRET_KEY=...
```
7. `fly deploy`

---

## 6. AWS / GCP / Azure (Cloud VMs)

### Option A: EC2 / Compute Engine / Azure VM
1. Launch a VM (Ubuntu 22.04+, 2+ vCPU, 4GB+ RAM)
2. Install Docker or Python directly
3. Clone repo and run:
```bash
sudo apt update && sudo apt install -y python3-pip git
git clone <repo>
cd "new python project"
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 2 --timeout 300 app:app
```
4. Use `systemd` or `pm2` to keep the process running
5. Configure Nginx as reverse proxy (optional but recommended)

### Option B: AWS Elastic Beanstalk
1. Zip the project (excluding `.git`, `__pycache__`, `*.mp4`, `*.pt`)
2. Create Elastic Beanstalk Python application
3. Upload zip
4. Configure environment variables in EB console
5. Set up an RDS or EFS if you need shared storage (otherwise SQLite on instance storage)

### Option C: Google Cloud Run
1. Ensure `Dockerfile` is present
2. `gcloud run deploy accident-detection --source . --region us-central1`
3. Set env vars and a persistent disk via Cloud Storage or Cloud SQL

---

## 7. DigitalOcean App Platform

1. Push to GitHub
2. Create new App in DigitalOcean
3. Connect repo → Auto-detects Docker
4. Set env vars
5. Add a Persistent Volume (1GB) mounted at `/app/data`
6. Deploy

---

## 8. Production Checklist

### 8.1 Environment Variables
| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session security |
| `PORT` | Yes | Server port |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram alerts |
| `TELEGRAM_CHAT_ID` | Yes | Telegram alerts |
| `ROBOFLOW_API_KEY` | Yes | Crash detection model |
| `ROBOFLOW_WORKSPACE` | Yes | Roboflow workspace |
| `ROBOFLOW_PROJECT` | Yes | Roboflow project |
| `ROBOFLOW_VERSION` | Yes | Model version |
| `DATA_DIR` | Yes | Persistent storage path |
| `SMTP_HOST` | No | Email alerts |
| `SMTP_PORT` | No | Email alerts |
| `SMTP_USER` | No | Email alerts |
| `SMTP_PASSWORD` | No | Email alerts |
| `FROM_EMAIL` | No | Email alerts |
| `TWILIO_ACCOUNT_SID` | No | SMS/WhatsApp alerts |
| `TWILIO_AUTH_TOKEN` | No | SMS/WhatsApp alerts |
| `TWILIO_FROM_PHONE` | No | SMS alerts |
| `TWILIO_FROM_WHATSAPP` | No | WhatsApp alerts |
| `CONFIDENCE` | No | YOLO confidence (default 0.5) |
| `PROCESS_EVERY_N_FRAMES` | No | Frame skip (default 2) |
| `CAMERA_LOCATION` | No | Default camera location |

### 8.2 Files to Exclude from Deployment
These are in `.dockerignore` / `.gitignore`:
- `accident_dashboard.db` (recreated on startup)
- `output/`, `uploads/`, `accident_frames/` (runtime data)
- `*.mp4`, `*.avi`, `*.mov` (video files)
- `*.pt` (model files — upload `yolov8n.pt` separately or use a model server)
- `.env` (secrets)
- `__pycache__/`, `.venv/`, `.git/`

### 8.3 Model File Handling
- `yolov8n.pt` (~6MB) is in the repo by default
- For production, consider:
  - Using YOLOv8n via `ultralytics` download (no file needed): `YOLO('yolov8n.pt')` downloads automatically
  - Or store the `.pt` file on persistent disk and set `MODEL_PATH` env var

### 8.4 Persistent Storage
The app creates these directories at runtime:
- `DATA_DIR/accident_frames/` — accident JPEGs
- `DATA_DIR/output/` — annotated videos + accident clips
- `DATA_DIR/uploads/` — user-uploaded videos
- `DATA_DIR/accident_dashboard.db` — SQLite database

**Ensure `DATA_DIR` is on persistent storage**, not ephemeral container filesystem.

### 8.5 Security Notes
- Change default password (`Dhiren@9974`) after first login
- Use strong `SECRET_KEY`
- Enable HTTPS (most platforms handle this automatically)
- Restrict CORS if embedding in another domain
- Never commit `.env` or secrets to version control

### 8.6 Scaling Considerations
- This app is **single-process**. For multiple concurrent detections, you need:
  - A task queue (Celery + Redis)
  - Separate workers for detection
  - A shared database (PostgreSQL instead of SQLite)
- For most single-location deployments, the current architecture is sufficient

---

## 9. Quick Deploy Commands

### Render
```bash
# Install Render CLI
npm install -g @render/cli

# Deploy
render deploy
```

### Railway
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

### Fly.io
```bash
fly launch
fly volumes create accident_data --size 1
fly secrets set TELEGRAM_BOT_TOKEN=... ROBOFLOW_API_KEY=...
fly deploy
```

### Docker (Any VPS / Dedicated Server)
```bash
docker build -t accident-detection .
docker run -d \
  -p 5000:5000 \
  -e SECRET_KEY=your_key \
  -e TELEGRAM_BOT_TOKEN=... \
  -e ROBOFLOW_API_KEY=... \
  -v /path/on/host/data:/app/data \
  --name accident-app \
  --restart unless-stopped \
  accident-detection
```

---

## 10. Post-Deployment Verification

```bash
# Health check (should return {"status":"ok",...})
curl https://your-domain.com/health

# Check app is running
curl https://your-domain.com/api/status

# Verify static files load
curl -I https://your-domain.com/css/style.css
curl -I https://your-domain.com/js/main.js

# Login test
curl -X POST https://your-domain.com/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Dhiren@9974"}'

# Check analytics
curl https://your-domain.com/api/analytics
```

After deployment, open the dashboard URL, log in, and verify:
1. Dashboard loads with stats
2. Settings page shows loaded configuration
3. Upload a test video and start detection
4. Verify Telegram/Email/SMS alerts are received (if configured)

### Troubleshooting "Not Found" Errors
- **Static files 404**: Ensure `website/` folder is present in the deployment. The app now serves `/css/style.css` and `/js/main.js` explicitly via Flask routes.
- **Dashboard blank**: Check browser console for 404s on `/css/style.css` or `/js/main.js`
- **Health check fails**: Ensure the container is running and port is correctly mapped
- **Database not persisting**: Verify `DATA_DIR` points to the persistent disk mount (e.g., `/app/data` on Render)
