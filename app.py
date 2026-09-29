import os
import time
import cv2
import numpy as np
from collections import deque
from ultralytics import YOLO
import requests
import warnings
from roboflow import Roboflow
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import threading
from datetime import datetime
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
import re

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

warnings.filterwarnings('ignore')
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv('DATA_DIR', BASE_DIR)

# ---------------- CONFIG ----------------
VIDEO_PATH = os.path.join(BASE_DIR, "Ford Figo crashes into Tata Punch, impact flips SUV dramatically on wet slippery road#bharat #in.mp4")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
SAVE_DIR = os.path.join(DATA_DIR, 'accident_frames')
os.makedirs(SAVE_DIR, exist_ok=True)
DISPLAY_VIDEO = False
SAVE_OUTPUT_VIDEO = True

UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
YOUTUBE_DIR = os.path.join(DATA_DIR, 'youtube')
os.makedirs(YOUTUBE_DIR, exist_ok=True)

# ---------------- YOUTUBE HELPERS ----------------
def is_youtube_url(url):
    return bool(re.search(r'(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)', url))

def download_youtube_video(url):
    if not YTDLP_AVAILABLE:
        raise Exception('yt-dlp is not installed. Please install it with: pip install yt-dlp')
    ydl_opts = {
        'outtmpl': os.path.join(YOUTUBE_DIR, '%(id)s.%(ext)s'),
        'format': 'best[ext=mp4][height<=720]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'max_filesize': 500 * 1024 * 1024,
        'socket_timeout': 60,
        'retries': 3,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, ext = os.path.splitext(filename)
            if ext != '.mp4' and os.path.exists(base + '.mp4'):
                filename = base + '.mp4'
            return filename, info.get('title', 'YouTube Video')
    except Exception as e:
        msg = str(e)
        if 'Sign in to confirm' in msg or 'bot' in msg.lower():
            raise Exception('YouTube blocked the download (bot detection). Try a different video or use Upload instead.')
        if '403' in msg or 'Forbidden' in msg:
            raise Exception('YouTube returned 403 Forbidden. The video may be age-restricted or region-locked.')
        if 'Video unavailable' in msg:
            raise Exception('YouTube video is unavailable (private, deleted, or region-locked).')
        raise Exception(f'YouTube download failed: {msg[:200]}')

# ---------------- DATABASE ----------------
DB_PATH = os.path.join(DATA_DIR, 'accident_dashboard.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        email TEXT,
        phone TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS accidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        frame_number INTEGER,
        timestamp TEXT,
        confidence REAL,
        vehicle_type TEXT,
        bbox TEXT,
        image_path TEXT,
        video_name TEXT,
        severity TEXT DEFAULT 'moderate',
        status TEXT DEFAULT 'pending',
        camera_location TEXT,
        operator_id INTEGER,
        operator_notes TEXT,
        response_details TEXT,
        video_clip_path TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS accident_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        accident_id INTEGER,
        operator_id INTEGER,
        action TEXT,
        notes TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (accident_id) REFERENCES accidents(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        recipient TEXT,
        message TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS video_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_path TEXT,
        source_type TEXT,
        status TEXT DEFAULT 'queued',
        priority INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car_count INTEGER DEFAULT 0,
        truck_count INTEGER DEFAULT 0,
        bus_count INTEGER DEFAULT 0,
        motorcycle_count INTEGER DEFAULT 0,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT UNIQUE NOT NULL,
        vehicle_type TEXT,
        make TEXT,
        model TEXT,
        color TEXT,
        year INTEGER,
        owner_name TEXT,
        owner_phone TEXT,
        owner_email TEXT,
        address TEXT,
        registration_date TEXT,
        insurance_expiry TEXT,
        notes TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS vehicle_detections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT,
        vehicle_type TEXT,
        bbox TEXT,
        image_path TEXT,
        video_name TEXT,
        owner_name TEXT,
        owner_phone TEXT,
        confidence REAL,
        status TEXT DEFAULT 'pending',
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)', ('admin', 'Dhiren@9974', 'admin'))
    _seed_demo_vehicles(c)
    conn.commit()
    conn.close()

def _seed_demo_vehicles(c):
    demo_vehicles = [
        ('MH01AB1234', 'car', 'Maruti', 'Swift', 'White', 2019, 'Rahul Sharma', '9876543210', 'rahul@example.com', 'Andheri, Mumbai', '2021-03-12', '2027-03-11', 'Regular commuter'),
        ('DL05CD5678', 'car', 'Hyundai', 'i20', 'Silver', 2020, 'Priya Singh', '9123456780', 'priya@example.com', 'Karol Bagh, Delhi', '2020-07-01', '2026-06-30', 'Corporate fleet'),
        ('KA02EF9012', 'truck', 'Tata', 'Signa', 'Blue', 2018, 'Kumar Logistics', '9988776655', 'kumar@logistics.com', 'Peenya, Bengaluru', '2019-01-20', '2025-12-31', 'Goods carrier'),
        ('TN09GH3456', 'bus', 'Ashok Leyland', 'Viking', 'Red', 2017, 'Omni Travels', '9888665544', 'ops@omnitravels.com', 'Tambaram, Chennai', '2018-05-15', '2026-05-14', 'Passenger service'),
        ('GJ01JK7890', 'motorcycle', 'Royal Enfield', 'Classic 350', 'Black', 2022, 'Amit Patel', '9090909090', 'amit@example.com', 'Navrangpura, Ahmedabad', '2022-09-09', '2028-09-08', 'Personal use'),
    ]
    for v in demo_vehicles:
        c.execute('''INSERT OR IGNORE INTO vehicles
            (plate_number, vehicle_type, make, model, color, year, owner_name, owner_phone, owner_email, address, registration_date, insurance_expiry, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', v)

def lookup_vehicle_owner(plate_number):
    if not plate_number:
        return None
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM vehicles WHERE plate_number = ?', (plate_number,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def migrate_db():
    conn = get_db()
    c = conn.cursor()
    columns_to_add = {
        'accidents': [
            ('severity', 'TEXT DEFAULT "moderate"'),
            ('status', 'TEXT DEFAULT "pending"'),
            ('camera_location', 'TEXT'),
            ('operator_id', 'INTEGER'),
            ('operator_notes', 'TEXT'),
            ('response_details', 'TEXT'),
            ('video_clip_path', 'TEXT')
        ]
    }
    for table, columns in columns_to_add.items():
        c.execute(f"PRAGMA table_info({table})")
        existing_columns = [row['name'] for row in c.fetchall()]
        for col_name, col_type in columns:
            if col_name not in existing_columns:
                try:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                except Exception as e:
                    print(f"[WARNING] Migration failed for {table}.{col_name}: {e}")
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS accident_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accident_id INTEGER,
            operator_id INTEGER,
            action TEXT,
            notes TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (accident_id) REFERENCES accidents(id)
        )''')
    except Exception as e:
        print(f"[WARNING] Failed to create accident_responses table: {e}")
    conn.commit()
    conn.close()

migrate_db()
init_db()  # Initialize database before any get_setting calls

def get_setting(key, default=None):
    env_mappings = {
        'telegram_bot_token': 'TELEGRAM_BOT_TOKEN',
        'telegram_chat_id': 'TELEGRAM_CHAT_ID',
        'roboflow_api_key': 'ROBOFLOW_API_KEY',
        'roboflow_workspace': 'ROBOFLOW_WORKSPACE',
        'roboflow_project': 'ROBOFLOW_PROJECT',
        'confidence_threshold': 'CONFIDENCE',
        'smtp_host': 'SMTP_HOST',
        'smtp_port': 'SMTP_PORT',
        'smtp_user': 'SMTP_USER',
        'smtp_password': 'SMTP_PASSWORD',
        'from_email': 'FROM_EMAIL',
        'twilio_account_sid': 'TWILIO_ACCOUNT_SID',
        'twilio_auth_token': 'TWILIO_AUTH_TOKEN',
        'twilio_from_phone': 'TWILIO_FROM_PHONE',
        'twilio_from_whatsapp': 'TWILIO_FROM_WHATSAPP',
        'alert_recipient_emails': 'ALERT_RECIPIENT_EMAILS',
        'alert_recipient_sms': 'ALERT_RECIPIENT_SMS',
        'alert_recipient_whatsapp': 'ALERT_RECIPIENT_WHATSAPP',
    }
    env_key = env_mappings.get(key, key.upper())
    env_value = os.getenv(env_key)
    if env_value is not None and env_value != '':
        return str(env_value)
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    if row and row['value'] is not None and row['value'] != '':
        return row['value']
    return default

# ---------------- TELEGRAM CONFIGURATION ----------------
BOT_TOKEN = get_setting('telegram_bot_token', '')
CHAT_ID = get_setting('telegram_chat_id', '')
NOTIFICATION_COOLDOWN = int(get_setting('notification_cooldown', 60))

# ---------------- ROBOFLOW CONFIGURATION ----------------
ROBOFLOW_API_KEY = get_setting('roboflow_api_key', '')
ROBOFLOW_WORKSPACE = get_setting('roboflow_workspace', '')
ROBOFLOW_PROJECT = get_setting('roboflow_project', '')
ROBOFLOW_VERSION = int(get_setting('roboflow_version', 1))

# ---------------- DETECTION PARAMETERS ----------------
MODEL_PATH = os.path.join(BASE_DIR, 'yolov8s.pt')
CONFIDENCE = float(get_setting('confidence_threshold', 0.35))
PROCESS_EVERY_N_FRAMES = max(1, int(get_setting('process_every_n_frames', 1)))
CRASH_CONFIDENCE_THRESHOLD = float(get_setting('crash_confidence_threshold', 0.35))
IOU_MATCH_THRESHOLD = float(get_setting('iou_match_threshold', 0.3))
MAX_LOST_FRAMES = int(get_setting('max_lost_frames', 5))
DETECTION_SPEED = get_setting('detection_speed', 'normal')

# ---------------- LICENSE PLATE RECOGNITION ----------------
PLATE_DIR = os.path.join(DATA_DIR, 'plate_frames')
os.makedirs(PLATE_DIR, exist_ok=True)
PLATE_DETECT_INTERVAL = int(get_setting('plate_detect_interval', 30))
PLATE_MIN_AREA = int(get_setting('plate_min_area', 1500))
PLATE_MAX_ASPECT = float(get_setting('plate_max_aspect', 7.0))
PLATE_MIN_ASPECT = float(get_setting('plate_min_aspect', 1.8))

# ---------------- FLASK APP ----------------
app = Flask(__name__, static_folder='website', static_url_path='')
CORS(app)

# ---------------- ERROR HANDLERS ----------------
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'message': 'API endpoint not found'}), 404
    return send_from_directory(os.path.join(BASE_DIR, 'website'), 'index.html')

@app.errorhandler(500)
def server_error(e):
    return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

# ---------------- HEALTH CHECK ----------------
@app.route('/health')
def health_check():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

# ---------------- LOGIN CONFIG ----------------
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())
login_manager = LoginManager(app)
login_manager.login_view = 'api_login'

class User(UserMixin):
    def __init__(self, id_, username, role, email=None, phone=None):
        self.id = id_
        self.username = username
        self.role = role
        self.email = email or ''
        self.phone = phone or ''

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return User(row['id'], row['username'], row['role'], row['email'], row['phone'])
    return None

# ---------------- GLOBAL STATE ----------------
state = {
    'status': 'idle',
    'progress': 0,
    'total_frames': 0,
    'processed_frames': 0,
    'total_accidents': 0,
    'current_video': None,
    'accident_frames': [],
    'output_video': None,
    'detected_plates': 0,
    'recent_plates': [],
    'avg_fps': 0,
    'error': None,
    'start_time': None,
    'end_time': None
}
state_lock = threading.Lock()
detection_thread = None
video_queue_thread = None
vehicle_counts_state = {'car': 0, 'truck': 0, 'bus': 0, 'motorcycle': 0, 'timestamp': None}

# ---------------- MODEL INITIALIZATION ----------------
yolo_model = None
crash_model = None

if os.path.exists(MODEL_PATH):
    print("[INFO] Loading YOLO model...")
    yolo_model = YOLO(MODEL_PATH, verbose=False)
    yolo_model.overrides['verbose'] = False
else:
    print(f"[WARNING] YOLO model not found at {MODEL_PATH}")

try:
    rf = Roboflow(api_key=ROBOFLOW_API_KEY)
    project = rf.workspace(ROBOFLOW_WORKSPACE).project(ROBOFLOW_PROJECT)
    crash_model = project.version(ROBOFLOW_VERSION).model
    print("[INFO] Roboflow crash detection model loaded successfully!")
except Exception as e:
    print(f"[WARNING] Failed to load Roboflow model: {e}")

# ---------------- ALERT SYSTEM ----------------
class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id
        self.last_notification_time = 0

    def send_emergency_alert(self, accidents):
        if not self.chat_id:
            return
        now = time.time()
        if now - self.last_notification_time < NOTIFICATION_COOLDOWN:
            return
        self.last_notification_time = now
        message = f"ACCIDENT ALERT\nTotal Incidents: {len(accidents)}"
        for acc in accidents:
            sev = acc.get('severity', 'unknown').upper()
            message += f"\n- Type: {acc.get('type', 'vehicle')} | Severity: {sev} | Confidence: {acc.get('confidence', 0):.2f}"
        try:
            requests.post(self.url, data={
                "chat_id": self.chat_id,
                "text": message
            }, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send Telegram alert: {e}")

class EmailNotifier:
    def __init__(self):
        self.reload()

    def reload(self):
        self.smtp_host = get_setting('smtp_host', '')
        self.smtp_port = int(get_setting('smtp_port', 587))
        self.smtp_user = get_setting('smtp_user', '')
        self.smtp_password = get_setting('smtp_password', '')
        self.from_email = get_setting('from_email', '')

    def is_configured(self):
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.from_email)

    def send_alert(self, to_email, subject, body):
        self.reload()
        if not self.is_configured():
            print("[WARNING] Email not configured")
            return False, 'not configured'
        msg = MIMEMultipart()
        msg['From'] = self.from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        use_ssl = self.smtp_port == 465
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            server.ehlo()
            if not use_ssl:
                server.starttls()
                server.ehlo()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
            server.quit()
            return True, ''
        except Exception as e:
            print(f"[ERROR] Email SSL attempt failed: {e}")
            if not use_ssl:
                try:
                    server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30)
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
                    server.quit()
                    return True, ''
                except Exception as e2:
                    print(f"[ERROR] Email SSL fallback failed: {e2}")
                    return False, str(e2)
            return False, str(e)

class SMSNotifier:
    def __init__(self):
        self.account_sid = get_setting('twilio_account_sid', '')
        self.auth_token = get_setting('twilio_auth_token', '')
        self.from_phone = get_setting('twilio_from_phone', '')

    def is_configured(self):
        return bool(self.account_sid and self.auth_token and self.from_phone)

    def send_alert(self, to_phone, message):
        if not self.is_configured():
            print("[WARNING] SMS not configured")
            return False
        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            client.messages.create(body=message, from_=self.from_phone, to=to_phone)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to send SMS: {e}")
            return False

class WhatsAppNotifier:
    def __init__(self):
        self.account_sid = get_setting('twilio_account_sid', '')
        self.auth_token = get_setting('twilio_auth_token', '')
        self.from_whatsapp = get_setting('twilio_from_whatsapp', '')

    def is_configured(self):
        return bool(self.account_sid and self.auth_token and self.from_whatsapp)

    def send_alert(self, to_whatsapp, message):
        if not self.is_configured():
            print("[WARNING] WhatsApp not configured")
            return False
        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            client.messages.create(body=message, from_=self.from_whatsapp, to=to_whatsapp)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to send WhatsApp: {e}")
            return False

email_notifier = EmailNotifier()
sms_notifier = SMSNotifier()
whatsapp_notifier = WhatsAppNotifier()


def send_all_notifications(accidents, frame_number, camera_location):
    """Send accident alerts through every configured channel: email, SMS, WhatsApp."""
    recipients = (get_setting('alert_recipient_emails', '') or '').strip()
    sms_recipients = (get_setting('alert_recipient_sms', '') or '').strip()
    wa_recipients = (get_setting('alert_recipient_whatsapp', '') or '').strip()
    print(f"[NOTIFY] recipients: email='{recipients}' sms='{sms_recipients}' wa='{wa_recipients}'")

    if not recipients and not sms_recipients and not wa_recipients:
        print("[NOTIFY] No recipients configured, skipping alerts")
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    summary_lines = [f"- Frame {a.get('type', 'unknown')} | Severity: {a.get('severity', 'moderate')} | Confidence: {round(float(a.get('confidence', 0)) * 100, 1)}%" for a in accidents]
    subject = f"[ACCIDENT ALERT] {len(accidents)} detected at {camera_location} (frame {frame_number})"
    body = (
        f"Accident detected!\n\n"
        f"Time: {timestamp}\n"
        f"Location: {camera_location}\n"
        f"Frame: {frame_number}\n"
        f"Count: {len(accidents)}\n\n"
        f"Details:\n" + "\n".join(summary_lines) +
        f"\n\nView dashboard: http://localhost:5000\n"
    )
    short_msg = f"ACCIDENT ALERT @ {camera_location} frame {frame_number} | {len(accidents)} detected | {timestamp}"

    if email_notifier.is_configured() and recipients:
        for addr in [r.strip() for r in recipients.split(',') if r.strip()]:
            ok, msg = email_notifier.send_alert(addr, subject, body)
            print(f"[NOTIFY] Email to {addr}: {'sent' if ok else 'failed - ' + msg}")

    if sms_notifier.is_configured() and sms_recipients:
        for phone in [r.strip() for r in sms_recipients.split(',') if r.strip()]:
            ok = sms_notifier.send_alert(phone, short_msg)
            print(f"[NOTIFY] SMS to {phone}: {'sent' if ok else 'failed'}")

    if whatsapp_notifier.is_configured() and wa_recipients:
        for phone in [r.strip() for r in wa_recipients.split(',') if r.strip()]:
            ok = whatsapp_notifier.send_alert(phone, short_msg)
            print(f"[NOTIFY] WhatsApp to {phone}: {'sent' if ok else 'failed'}")

# ---------------- TRACKER ----------------
def compute_iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    area2 = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0


def box_distance(box1, box2):
    """Minimum distance between two bounding boxes (in pixels)."""
    dx = max(box2[0] - box1[2], box1[0] - box2[2], 0)
    dy = max(box2[1] - box1[3], box1[1] - box2[3], 0)
    return (dx ** 2 + dy ** 2) ** 0.5

class OptimizedVehicleTracker:
    def __init__(self):
        self.tracks = {}
        self.next_id = 0

    def update(self, detections):
        updated_tracks = {}
        used_track_ids = set()
        for det in detections:
            best_iou = 0
            best_track_id = None
            for tid, track in self.tracks.items():
                if tid in used_track_ids:
                    continue
                iou = compute_iou(det[:4], track["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = tid
            if best_track_id is not None and best_iou >= IOU_MATCH_THRESHOLD:
                track = self.tracks[best_track_id]
                track["bbox"] = det[:4]
                track["class"] = det[4]
                track["is_moving"] = True
                track["lost"] = 0
                updated_tracks[best_track_id] = track
                used_track_ids.add(best_track_id)
            else:
                self.tracks[self.next_id] = {
                    "bbox": det[:4],
                    "class": det[4],
                    "is_moving": True,
                    "lost": 0
                }
                updated_tracks[self.next_id] = self.tracks[self.next_id]
                used_track_ids.add(self.next_id)
                self.next_id += 1
        for tid in list(self.tracks.keys()):
            if tid not in used_track_ids:
                self.tracks[tid]["lost"] += 1
                if self.tracks[tid]["lost"] <= MAX_LOST_FRAMES:
                    updated_tracks[tid] = self.tracks[tid]
                else:
                    del self.tracks[tid]
        return updated_tracks

# ---------------- ACCIDENT ANALYZER ----------------
class OptimizedAccidentAnalyzer:
    def __init__(self, crash_model=None):
        self.crash_model = crash_model

    @staticmethod
    def _refine_vehicle_class(track):
        """Use aspect ratio to fix YOLO's common car/truck/bus misclassifications."""
        cls = (track.get('class') or '').lower()
        if cls not in ('car', 'truck', 'bus'):
            return cls
        bbox = track.get('bbox')
        if not bbox or len(bbox) != 4:
            return cls
        try:
            w = max(bbox[2] - bbox[0], 1)
            h = max(bbox[3] - bbox[1], 1)
        except Exception:
            return cls
        aspect = w / h
        if cls == 'car' and aspect > 2.4:
            return 'truck' if aspect > 3.2 else 'bus'
        if cls == 'truck' and aspect < 1.8:
            return 'car'
        if cls == 'bus' and aspect < 1.4:
            return 'car'
        return cls

    def _compute_severity(self, iou, crash_conf, t1, t2):
        severe_vehicles = {'truck', 'bus'}
        t1_cls = self._refine_vehicle_class(t1)
        t2_cls = self._refine_vehicle_class(t2)
        if iou > 0.6 or crash_conf > 0.7 or (t1_cls in severe_vehicles and iou > 0.4) or (t2_cls in severe_vehicles and iou > 0.4):
            return 'critical'
        if iou > 0.4 or crash_conf > 0.5 or (t1_cls in severe_vehicles and iou > 0.25) or (t2_cls in severe_vehicles and iou > 0.25):
            return 'moderate'
        return 'minor'

    def analyze_accidents(self, frame, tracks, frame_number):
        accidents = []
        if len(tracks) < 2:
            return accidents
        track_items = list(tracks.items())
        for i in range(len(track_items)):
            for j in range(i + 1, len(track_items)):
                tid1, t1 = track_items[i]
                tid2, t2 = track_items[j]
                iou = compute_iou(t1["bbox"], t2["bbox"])
                bbox_dist = box_distance(t1["bbox"], t2["bbox"])
                if iou < 0.05 and bbox_dist > 80:
                    continue
                x1 = int(min(t1["bbox"][0], t2["bbox"][0]))
                y1 = int(min(t1["bbox"][1], t2["bbox"][1]))
                x2 = int(max(t1["bbox"][2], t2["bbox"][2]))
                y2 = int(max(t1["bbox"][3], t2["bbox"][3]))
                pad = 20
                x1 = max(0, x1 - pad)
                y1 = max(0, y1 - pad)
                x2 = min(frame.shape[1], x2 + pad)
                y2 = min(frame.shape[0], y2 + pad)
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                crash_conf = 0.0
                if self.crash_model is not None:
                    try:
                        pred = self.crash_model.predict(crop, confidence=5, overlap=30).json()
                        for p in pred.get("predictions", []):
                            if p.get("class", "").lower() in ("crash", "accident"):
                                crash_conf = max(crash_conf, p.get("confidence", 0.0))
                    except Exception as e:
                        print(f"[WARNING] Roboflow inference failed on frame {frame_number}: {e}")
                # Trigger if EITHER Roboflow says crash OR IoU indicates significant overlap
                if crash_conf >= CRASH_CONFIDENCE_THRESHOLD or iou > 0.35:
                    severity = self._compute_severity(iou, crash_conf, t1, t2)
                    accidents.append({
                        "bbox": (x1, y1, x2, y2),
                        "confidence": max(crash_conf, iou),
                        "type": f"{t1_cls}-{t2_cls}",
                        "severity": severity,
                        "crash_confidence": crash_conf,
                        "iou": iou
                    })
        return accidents

# ---------------- VISUALIZATION ----------------
def draw_optimized_visualization(frame, tracks, accidents, frame_number):
    for track_id, track in tracks.items():
        x1, y1, x2, y2 = map(int, track['bbox'])
        color = (0, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"ID:{track_id}"
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    for accident in accidents:
        x1, y1, x2, y2 = map(int, accident['bbox'])
        severity = accident.get('severity', 'moderate')
        if severity == 'critical':
            color = (0, 0, 255)
        elif severity == 'moderate':
            color = (0, 165, 255)
        else:
            color = (0, 215, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)
        label = f"ACCIDENT! {severity.upper()} ({accident['confidence']:.1f})"
        cv2.putText(frame, label, (x1, y1 - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    info_text = f"Frame: {frame_number} | Tracks: {len(tracks)}"
    if accidents:
        info_text += f" | ACCIDENTS: {len(accidents)}"
    cv2.putText(frame, info_text, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return frame

# ---------------- LICENSE PLATE RECOGNITION ----------------
class LicensePlateSystem:
    def __init__(self):
        self.ocr_engine = None
        self.ocr_name = 'none'
        try:
            import pytesseract
            self.ocr_engine = pytesseract
            self.ocr_name = 'pytesseract'
        except ImportError:
            try:
                import easyocr
                self.ocr_engine = easyocr.Reader(['en'], verbose=False)
                self.ocr_name = 'easyocr'
            except ImportError:
                self.ocr_engine = None
                self.ocr_name = 'none'

    def locate_plates(self, vehicle_crop):
        if vehicle_crop is None or vehicle_crop.size == 0:
            return []
        h, w = vehicle_crop.shape[:2]
        if h < 20 or w < 20:
            return []
        gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        edged = cv2.convertScaleAbs(edged)
        edged = cv2.GaussianBlur(edged, (5, 5), 0)
        _, thresh = cv2.threshold(edged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            aspect = cw / float(ch) if ch > 0 else 0
            if area < PLATE_MIN_AREA:
                continue
            if not (PLATE_MIN_ASPECT <= aspect <= PLATE_MAX_ASPECT):
                continue
            if y + ch > h or x + cw > w:
                continue
            candidates.append((x, y, x + cw, y + ch, area))
        candidates.sort(key=lambda c: c[4], reverse=True)
        return [(c[0], c[1], c[2], c[3]) for c in candidates[:3]]

    def recognize(self, plate_crop):
        if plate_crop is None or plate_crop.size == 0:
            return ''
        if self.ocr_name == 'none':
            return ''
        try:
            if self.ocr_name == 'pytesseract':
                cfg = '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                text = self.ocr_engine.image_to_string(plate_crop, config=cfg)
            else:
                results = self.ocr_engine.readtext(plate_crop, detail=0)
                text = ' '.join(results)
            cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
            return cleaned
        except Exception as e:
            print(f"[WARNING] Plate OCR failed: {e}")
            return ''

plate_system = LicensePlateSystem()

def process_vehicle_plates(frame, tracks, frame_number, current_video):
    last_plate = process_vehicle_plates.last_plate if hasattr(process_vehicle_plates, 'last_plate') else {}
    detected = []
    for tid, track in tracks.items():
        prev = last_plate.get(tid, -PLATE_DETECT_INTERVAL)
        if frame_number - prev < PLATE_DETECT_INTERVAL:
            continue
        last_plate[tid] = frame_number
        x1, y1, x2, y2 = map(int, track['bbox'])
        vehicle_crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
        if vehicle_crop.size == 0:
            continue
        regions = plate_system.locate_plates(vehicle_crop)
        if not regions:
            continue
        px1, py1, px2, py2 = regions[0]
        plate_crop = vehicle_crop[py1:py2, px1:px2]
        if plate_crop.size == 0:
            continue
        plate_text = plate_system.recognize(plate_crop)
        owner = lookup_vehicle_owner(plate_text) if plate_text else None
        plate_img_name = f"plate_{frame_number}_{tid}.jpg"
        try:
            cv2.imwrite(os.path.join(PLATE_DIR, plate_img_name), plate_crop)
        except Exception as e:
            print(f"[WARNING] Failed to save plate crop: {e}")
            plate_img_name = ''
        status = 'recognized' if plate_text else 'pending'
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO vehicle_detections
            (plate_number, vehicle_type, bbox, image_path, video_name, owner_name, owner_phone, confidence, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (plate_text, track['class'], f"{x1},{y1},{x2},{y2}", plate_img_name, current_video,
             owner['owner_name'] if owner else None, owner['owner_phone'] if owner else None,
             0.0 if not plate_text else 0.9, status, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        record = {
            'plate_number': plate_text,
            'vehicle_type': track['class'],
            'image_path': plate_img_name,
            'owner_name': owner['owner_name'] if owner else None,
            'status': status,
            'frame': frame_number
        }
        detected.append(record)
    process_vehicle_plates.last_plate = last_plate
    return detected

# ---------------- CORE DETECTION FUNCTION ----------------
def run_detection(video_path=None, source_type='file'):
    global state, vehicle_counts_state
    if video_path is None:
        video_path = VIDEO_PATH
    with state_lock:
        state['status'] = 'processing'
        state['progress'] = 0
        state['total_frames'] = 0
        state['processed_frames'] = 0
        state['total_accidents'] = 0
        state['current_video'] = os.path.basename(video_path) if source_type == 'file' else video_path
        state['accident_frames'] = []
        state['output_video'] = None
        state['detected_plates'] = 0
        state['recent_plates'] = []
        state['avg_fps'] = 0
        state['error'] = None
        state['start_time'] = datetime.now().isoformat()
        state['end_time'] = None
    if source_type == 'file' and not os.path.exists(video_path):
        with state_lock:
            state['status'] = 'error'
            state['error'] = f"Video file not found: {video_path}"
        return
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        with state_lock:
            state['status'] = 'error'
            state['error'] = f"Could not open video: {video_path}"
        return
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    with state_lock:
        state['total_frames'] = total_frames
    notifier = TelegramNotifier(BOT_TOKEN, CHAT_ID)
    tracker = OptimizedVehicleTracker()
    analyzer = OptimizedAccidentAnalyzer(crash_model)
    video_writer = None
    if SAVE_OUTPUT_VIDEO:
        output_fps = max(1, int(fps / PROCESS_EVERY_N_FRAMES))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        output_path = os.path.join(OUTPUT_DIR, f"telegram_accident_output_{int(time.time())}.mp4")
        video_writer = cv2.VideoWriter(output_path, fourcc, output_fps, (width, height))
        if not video_writer.isOpened():
            print(f"[ERROR] Failed to open VideoWriter for {output_path}")
            video_writer = None
    frame_buffer = deque(maxlen=90)
    clip_writer = None
    clip_path = None
    clip_frames_remaining = 0
    CLIP_DURATION = 30
    frame_number, processed_frames, total_accidents = 0, 0, 0
    processing_times = []
    camera_location = get_setting('camera_location', 'Unknown')
    process_vehicle_plates.last_plate = {}
    print("[INFO] Starting video processing...")
    while True:
        start_time = time.time()
        ret, frame = cap.read()
        if not ret:
            break
        frame_number += 1
        if frame_number % PROCESS_EVERY_N_FRAMES != 0:
            continue
        frame_buffer.append(frame.copy())
        if clip_writer is not None and clip_frames_remaining > 0:
            clip_writer.write(frame)
            clip_frames_remaining -= 1
            if clip_frames_remaining <= 0 and clip_writer is not None:
                clip_writer.release()
                clip_writer = None
                if clip_path:
                    print(f"[INFO] Saved accident clip: {clip_path}")
                    clip_path = None
        processed_frames += 1
        with state_lock:
            state['processed_frames'] = processed_frames
            if total_frames > 0:
                state['progress'] = int((frame_number / total_frames) * 100)
        detections = []
        vehicle_counts = {'car': 0, 'truck': 0, 'bus': 0, 'motorcycle': 0}
        try:
            if yolo_model is None:
                print("[ERROR] YOLO model not loaded")
                break
            results = yolo_model(frame, conf=CONFIDENCE, imgsz=640, verbose=False)[0]
            if hasattr(results, 'boxes') and len(results.boxes) > 0:
                boxes = results.boxes.xyxy.cpu().numpy()
                classes = results.boxes.cls.cpu().numpy().astype(int)
                for box, cls in zip(boxes, classes):
                    class_name = yolo_model.names[int(cls)]
                    if class_name in {'car', 'truck', 'bus', 'motorcycle', 'bicycle'}:
                        x1, y1, x2, y2 = map(int, box)
                        if (x2 - x1) * (y2 - y1) > 1000:
                            detections.append((x1, y1, x2, y2, class_name))
                            vehicle_counts[class_name] = vehicle_counts.get(class_name, 0) + 1
        except Exception as e:
            print(f"[WARNING] Detection failed on frame {frame_number}: {e}")
        with state_lock:
            vehicle_counts_state['car'] = vehicle_counts.get('car', 0)
            vehicle_counts_state['truck'] = vehicle_counts.get('truck', 0)
            vehicle_counts_state['bus'] = vehicle_counts.get('bus', 0)
            vehicle_counts_state['motorcycle'] = vehicle_counts.get('motorcycle', 0)
            vehicle_counts_state['timestamp'] = datetime.now().isoformat()
        tracks = tracker.update(detections)
        accidents = analyzer.analyze_accidents(frame, tracks, frame_number)
        if accidents:
            total_accidents += len(accidents)
            notifier.send_emergency_alert(accidents)
            print(f"[NOTIFY] Calling send_all_notifications for {len(accidents)} accidents at frame {frame_number}")
            send_all_notifications(accidents, frame_number, camera_location)
            print(f"[ACCIDENT] Frame {frame_number}: {len(accidents)} accident(s)")
            for idx, accident in enumerate(accidents):
                x1, y1, x2, y2 = map(int, accident['bbox'])
                frame_save_path = os.path.join(SAVE_DIR, f"accident_frame_{frame_number}_{idx}.jpg")
                try:
                    cv2.imwrite(frame_save_path, frame[y1:y2, x1:x2] if y2 > y1 and x2 > x1 else frame)
                    with state_lock:
                        state['accident_frames'].append({
                            'path': f"/accident_frames/accident_frame_{frame_number}_{idx}.jpg",
                            'frame': frame_number,
                            'confidence': round(float(accident['confidence']), 2),
                            'type': accident['type'],
                            'severity': accident.get('severity', 'moderate')
                        })
                        if len(state['accident_frames']) > 200:
                            state['accident_frames'] = state['accident_frames'][-200:]
                    clip_filename = None
                    if clip_writer is None:
                        clip_filename = f"accident_clip_{frame_number}_{idx}.mp4"
                        clip_path = os.path.join(OUTPUT_DIR, clip_filename)
                        clip_writer = cv2.VideoWriter(clip_path, cv2.VideoWriter_fourcc(*'mp4v'), max(1, int(fps / PROCESS_EVERY_N_FRAMES)), (width, height))
                        if clip_writer.isOpened():
                            for buffered_frame in frame_buffer:
                                clip_writer.write(buffered_frame)
                            clip_frames_remaining = CLIP_DURATION
                        else:
                            clip_writer = None
                            clip_filename = None
                    conn = get_db()
                    c = conn.cursor()
                    c.execute('''INSERT INTO accidents 
                        (frame_number, timestamp, confidence, vehicle_type, bbox, image_path, video_name, severity, status, camera_location, video_clip_path) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                              (frame_number, datetime.now().isoformat(), accident['confidence'], accident['type'],
                               f"{accident['bbox'][0]},{accident['bbox'][1]},{accident['bbox'][2]},{accident['bbox'][3]}",
                               f"accident_frame_{frame_number}_{idx}.jpg", state['current_video'],
                               accident.get('severity', 'moderate'), 'pending', camera_location, clip_filename))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"[WARNING] Failed to save accident frame: {e}")
        plate_reads = process_vehicle_plates(frame, tracks, frame_number, state['current_video'])
        if plate_reads:
            with state_lock:
                state['detected_plates'] += len(plate_reads)
                for pr in plate_reads:
                    state['recent_plates'].insert(0, pr)
                state['recent_plates'] = state['recent_plates'][:50]
        frame = draw_optimized_visualization(frame, tracks, accidents, frame_number)
        if video_writer:
            video_writer.write(frame)
        elapsed = time.time() - start_time
        processing_times.append(elapsed)
    avg_time = np.mean(processing_times) if processing_times else 0
    avg_fps = 1 / avg_time if avg_time > 0 else 0
    cap.release()
    if video_writer:
        video_writer.release()
    cv2.destroyAllWindows()
    with state_lock:
        state['status'] = 'complete'
        state['progress'] = 100
        state['total_accidents'] = total_accidents
        state['avg_fps'] = round(avg_fps, 2)
        state['end_time'] = datetime.now().isoformat()
        if video_writer:
            state['output_video'] = os.path.basename(output_path)
    print("[INFO] Processing complete.")
    print(f"[STATS] Total frames processed: {processed_frames}")
    print(f"[STATS] Total accidents detected: {total_accidents}")
    print(f"[STATS] Average FPS: {avg_fps:.2f}")

def process_queue():
    global video_queue_thread
    while True:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM video_queue WHERE status = "queued" ORDER BY priority DESC, created_at ASC LIMIT 1')
        row = c.fetchone()
        if row:
            c.execute('UPDATE video_queue SET status = "processing" WHERE id = ?', (row['id'],))
            conn.commit()
            conn.close()
            run_detection(row['video_path'])
        else:
            conn.close()
        time.sleep(2)

def start_queue_processor():
    global video_queue_thread
    if video_queue_thread is None or not video_queue_thread.is_alive():
        video_queue_thread = threading.Thread(target=process_queue, daemon=True)
        video_queue_thread.start()

def start_detection_thread(video_path=None, source_type='file'):
    global detection_thread
    if detection_thread and detection_thread.is_alive():
        return False, "Detection already in progress"
    detection_thread = threading.Thread(target=run_detection, args=(video_path, source_type), daemon=True)
    detection_thread.start()
    return True, "Detection started"

# ---------------- ROUTES ----------------
@app.route('/')
def index():
    return send_from_directory(os.path.join(BASE_DIR, 'website'), 'index.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/css/style.css')
def serve_css():
    return send_from_directory(os.path.join(BASE_DIR, 'website', 'css'), 'style.css')

@app.route('/js/main.js')
def serve_js():
    return send_from_directory(os.path.join(BASE_DIR, 'website', 'js'), 'main.js')

@app.route('/api/status')
def api_status():
    with state_lock:
        status_data = {k: v for k, v in state.items() if k != 'accident_frames'}
    status_data['saved_frames_count'] = len(state['accident_frames'])
    return jsonify(status_data)

@app.route('/api/detect', methods=['POST'])
@login_required
def api_detect():
    video_path = None
    source_type = 'file'
    if 'video' in request.files:
        file = request.files['video']
        if file.filename:
            filename = secure_filename(file.filename)
            video_path = os.path.join(UPLOAD_DIR, f"{int(time.time())}_{filename}")
            file.save(video_path)
            source_type = 'upload'
    elif request.json and 'source' in request.json:
        source = request.json['source']
        if source.startswith('rtsp://'):
            video_path = source
            source_type = 'rtsp'
        elif is_youtube_url(source):
            if not YTDLP_AVAILABLE:
                return jsonify({'status': 'error', 'message': 'YouTube support requires yt-dlp. Install with: pip install yt-dlp'}), 400
            try:
                video_path, title = download_youtube_video(source)
                source_type = 'youtube'
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Failed to download YouTube video: {str(e)}'}), 400
        elif source.startswith('http://') or source.startswith('https://'):
            video_path = source
            source_type = 'ip_camera'
        else:
            try:
                int(source)
                video_path = source
                source_type = 'webcam'
            except ValueError:
                return jsonify({'status': 'error', 'message': 'Invalid source'}), 400
    if video_path is None:
        return jsonify({'status': 'error', 'message': 'No video source provided'}), 400
    success, message = start_detection_thread(video_path, source_type)
    if success:
        return jsonify({'status': 'started', 'message': message, 'source_type': source_type})
    else:
        return jsonify({'status': 'error', 'message': message}), 400

@app.route('/api/accidents', methods=['GET', 'POST'])
@login_required
def api_accidents():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'GET':
        if request.args.get('summary') == '1':
            c.execute('SELECT COUNT(*) AS total, SUM(CASE WHEN severity="critical" THEN 1 ELSE 0 END) AS critical, SUM(CASE WHEN severity="moderate" THEN 1 ELSE 0 END) AS moderate, SUM(CASE WHEN severity="minor" THEN 1 ELSE 0 END) AS minor FROM accidents')
            row = dict(c.fetchone())
            conn.close()
            return jsonify(row)
        if request.args.get('dashboard') == '1':
            c.execute('SELECT id, frame_number, timestamp, confidence, vehicle_type, status, severity, image_path FROM accidents ORDER BY timestamp DESC LIMIT 20')
            accidents = [dict(row) for row in c.fetchall()]
            conn.close()
            return jsonify(accidents)
        query = 'SELECT * FROM accidents WHERE 1=1'
        params = []
        vehicle = request.args.get('vehicle')
        if vehicle:
            query += ' AND vehicle_type LIKE ?'
            params.append(f'%{vehicle}%')
        try:
            limit = max(1, min(int(request.args.get('limit', 100)), 500))
        except (TypeError, ValueError):
            limit = 100
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        c.execute(query, params)
        accidents = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(accidents)
    elif request.method == 'POST':
        data = request.json
        c.execute('INSERT INTO accidents (frame_number, timestamp, confidence, vehicle_type, bbox, image_path, video_name) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (data.get('frame_number'), datetime.now().isoformat(),
                   data.get('confidence'), data.get('vehicle_type'),
                   data.get('bbox'), data.get('image_path'), data.get('video_name')))
        conn.commit()
        accident_id = c.lastrowid
        conn.close()
        return jsonify({'id': accident_id, 'status': 'created'}), 201

@app.route('/api/accidents/<int:accident_id>', methods=['DELETE'])
@login_required
def api_accident_delete(accident_id):
    if current_user.role != 'admin':
        return jsonify({'status': 'error', 'message': 'Admin access required'}), 403
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT image_path, video_clip_path FROM accidents WHERE id = ?', (accident_id,))
    row = c.fetchone()
    c.execute('DELETE FROM accidents WHERE id = ?', (accident_id,))
    conn.commit()
    conn.close()
    if row:
        try:
            if row['image_path']:
                img_path = os.path.join(SAVE_DIR, row['image_path'])
                if os.path.exists(img_path):
                    os.remove(img_path)
            if row['video_clip_path']:
                clip_path = os.path.join(OUTPUT_DIR, row['video_clip_path'])
                if os.path.exists(clip_path):
                    os.remove(clip_path)
        except Exception as e:
            print(f"[WARNING] Failed to delete accident files: {e}")
    return jsonify({'status': 'deleted'})

@app.route('/api/accidents/<int:accident_id>/confirm', methods=['PUT'])
@login_required
def api_accident_confirm(accident_id):
    if current_user.role not in ('admin', 'operator'):
        return jsonify({'status': 'error', 'message': 'Operator access required'}), 403
    data = request.json or {}
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE accidents SET status = ?, operator_notes = ?, operator_id = ? WHERE id = ?',
              ('confirmed', data.get('notes', ''), current_user.id, accident_id))
    c.execute('INSERT INTO accident_responses (accident_id, operator_id, action, notes) VALUES (?, ?, ?, ?)',
              (accident_id, current_user.id, 'confirmed', data.get('notes', '')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'confirmed'})

@app.route('/api/accidents/<int:accident_id>/false-alarm', methods=['PUT'])
@login_required
def api_accident_false_alarm(accident_id):
    if current_user.role not in ('admin', 'operator'):
        return jsonify({'status': 'error', 'message': 'Operator access required'}), 403
    data = request.json or {}
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE accidents SET status = ?, operator_notes = ?, operator_id = ? WHERE id = ?',
              ('false_alarm', data.get('notes', ''), current_user.id, accident_id))
    c.execute('INSERT INTO accident_responses (accident_id, operator_id, action, notes) VALUES (?, ?, ?, ?)',
              (accident_id, current_user.id, 'false_alarm', data.get('notes', '')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'marked_as_false_alarm'})

@app.route('/api/accidents/<int:accident_id>/emergency-response', methods=['PUT'])
@login_required
def api_accident_emergency_response(accident_id):
    if current_user.role not in ('admin', 'operator'):
        return jsonify({'status': 'error', 'message': 'Operator access required'}), 403
    data = request.json or {}
    conn = get_db()
    c = conn.cursor()
    response_details = data.get('response_details', '')
    c.execute('UPDATE accidents SET status = ?, operator_notes = ?, operator_id = ?, response_details = ? WHERE id = ?',
              ('emergency_response', data.get('notes', ''), current_user.id, response_details, accident_id))
    c.execute('INSERT INTO accident_responses (accident_id, operator_id, action, notes) VALUES (?, ?, ?, ?)',
              (accident_id, current_user.id, 'emergency_response', data.get('notes', '')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'emergency_initiated'})

@app.route('/api/accidents/responses/<int:accident_id>')
@login_required
def api_accident_responses(accident_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM accident_responses WHERE accident_id = ? ORDER BY timestamp DESC', (accident_id,))
    responses = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(responses)

@app.route('/api/analytics')
@login_required
def api_analytics():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT date(timestamp) as day, count(*) as count FROM accidents GROUP BY date(timestamp) ORDER BY day DESC LIMIT 30')
    accidents_per_day = {row['day']: row['count'] for row in c.fetchall()}
    c.execute('SELECT strftime("%H", timestamp) as hour, count(*) as count FROM accidents GROUP BY hour ORDER BY hour')
    accidents_per_hour = {row['hour']: row['count'] for row in c.fetchall()}
    c.execute('SELECT vehicle_type, count(*) as count FROM accidents GROUP BY vehicle_type')
    raw_type_counts = {row['vehicle_type']: row['count'] for row in c.fetchall()}
    vehicle_class_counts = {'car': 0, 'truck': 0, 'bus': 0, 'motorcycle': 0, 'other': 0}
    for vtype, cnt in raw_type_counts.items():
        for part in str(vtype).split('-'):
            part = part.strip().lower()
            if part in vehicle_class_counts:
                vehicle_class_counts[part] += cnt
            else:
                vehicle_class_counts['other'] += cnt
    c.execute('SELECT avg(confidence) as avg_conf FROM accidents')
    avg_confidence = c.fetchone()['avg_conf'] or 0
    c.execute('SELECT severity, count(*) as count FROM accidents GROUP BY severity')
    severity_counts = {row['severity']: row['count'] for row in c.fetchall()}
    c.execute('SELECT status, count(*) as count FROM accidents GROUP BY status')
    status_counts = {row['status']: row['count'] for row in c.fetchall()}
    c.execute('SELECT camera_location, count(*) as count FROM accidents GROUP BY camera_location')
    location_counts = {row['camera_location']: row['count'] for row in c.fetchall()}
    conn.close()
    return jsonify({
        'accidents_per_day': accidents_per_day,
        'accidents_per_hour': accidents_per_hour,
        'vehicle_type_counts': raw_type_counts,
        'vehicle_class_counts': vehicle_class_counts,
        'avg_confidence': round(avg_confidence, 2),
        'severity_counts': severity_counts,
        'status_counts': status_counts,
        'location_counts': location_counts
    })

@app.route('/api/settings', methods=['GET', 'PUT'])
@login_required
def api_settings():
    if current_user.role not in ('admin', 'operator'):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    conn = get_db()
    if request.method == 'GET':
        c = conn.cursor()
        c.execute('SELECT * FROM settings')
        settings = {row['key']: row['value'] for row in c.fetchall()}
        conn.close()
        env_defaults = {
            'telegram_bot_token': os.getenv('TELEGRAM_BOT_TOKEN', ''),
            'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
            'roboflow_api_key': os.getenv('ROBOFLOW_API_KEY', ''),
            'roboflow_workspace': os.getenv('ROBOFLOW_WORKSPACE', ''),
            'roboflow_project': os.getenv('ROBOFLOW_PROJECT', ''),
            'roboflow_version': os.getenv('ROBOFLOW_VERSION', ''),
            'smtp_host': os.getenv('SMTP_HOST', ''),
            'smtp_port': os.getenv('SMTP_PORT', ''),
            'smtp_user': os.getenv('SMTP_USER', ''),
            'smtp_password': os.getenv('SMTP_PASSWORD', ''),
            'from_email': os.getenv('FROM_EMAIL', ''),
            'twilio_account_sid': os.getenv('TWILIO_ACCOUNT_SID', ''),
            'twilio_auth_token': os.getenv('TWILIO_AUTH_TOKEN', ''),
            'twilio_from_phone': os.getenv('TWILIO_FROM_PHONE', ''),
            'twilio_from_whatsapp': os.getenv('TWILIO_FROM_WHATSAPP', ''),
            'alert_recipient_emails': os.getenv('ALERT_RECIPIENT_EMAILS', ''),
            'alert_recipient_sms': os.getenv('ALERT_RECIPIENT_SMS', ''),
            'alert_recipient_whatsapp': os.getenv('ALERT_RECIPIENT_WHATSAPP', ''),
        }
        for k, v in env_defaults.items():
            if v:
                settings[k] = v
                settings[k] = v
        return jsonify(settings)
    elif request.method == 'PUT':
        data = request.json
        c = conn.cursor()
        for key, value in data.items():
            c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        conn.commit()
        conn.close()
        return jsonify({'status': 'updated'})

@app.route('/api/vehicle/counts')
@login_required
def api_vehicle_counts():
    with state_lock:
        return jsonify(vehicle_counts_state)

# ---------------- VEHICLE / LICENSE PLATE ENDPOINTS ----------------
@app.route('/api/vehicles', methods=['GET', 'POST'])
@login_required
def api_vehicles():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'GET':
        plate = request.args.get('plate')
        if plate:
            c.execute('SELECT * FROM vehicles WHERE plate_number = ?', (plate,))
            row = c.fetchone()
            conn.close()
            return jsonify(dict(row) if row else None)
        c.execute('SELECT * FROM vehicles ORDER BY id DESC')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    elif request.method == 'POST':
        data = request.json or {}
        plate = (data.get('plate_number') or '').upper().strip()
        if not plate:
            return jsonify({'status': 'error', 'message': 'plate_number is required'}), 400
        c.execute('''INSERT OR REPLACE INTO vehicles
            (plate_number, vehicle_type, make, model, color, year, owner_name, owner_phone, owner_email, address, registration_date, insurance_expiry, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (plate, data.get('vehicle_type'), data.get('make'), data.get('model'), data.get('color'),
             data.get('year'), data.get('owner_name'), data.get('owner_phone'), data.get('owner_email'),
             data.get('address'), data.get('registration_date'), data.get('insurance_expiry'), data.get('notes')))
        conn.commit()
        conn.close()
        return jsonify({'status': 'saved', 'plate_number': plate}), 201

@app.route('/api/vehicles/<plate>', methods=['GET', 'DELETE'])
@login_required
def api_vehicle_detail(plate):
    conn = get_db()
    c = conn.cursor()
    if request.method == 'DELETE':
        if current_user.role != 'admin':
            return jsonify({'status': 'error', 'message': 'Admin access required'}), 403
        c.execute('DELETE FROM vehicles WHERE plate_number = ?', (plate,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'deleted'})
    c.execute('SELECT * FROM vehicles WHERE plate_number = ?', (plate,))
    row = c.fetchone()
    conn.close()
    return jsonify(dict(row) if row else None)

@app.route('/api/vehicle-detections', methods=['GET'])
@login_required
def api_vehicle_detections():
    conn = get_db()
    c = conn.cursor()
    limit = request.args.get('limit', default=100, type=int)
    c.execute('SELECT * FROM vehicle_detections ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/vehicle-detections/<int:detection_id>/confirm', methods=['PUT'])
@login_required
def api_vehicle_detection_confirm(detection_id):
    data = request.json or {}
    plate = (data.get('plate_number') or '').upper().strip()
    conn = get_db()
    c = conn.cursor()
    owner = lookup_vehicle_owner(plate) if plate else None
    c.execute('UPDATE vehicle_detections SET plate_number = ?, owner_name = ?, owner_phone = ?, status = ? WHERE id = ?',
              (plate, owner['owner_name'] if owner else None, owner['owner_phone'] if owner else None,
               'recognized' if plate else 'pending', detection_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'updated', 'plate_number': plate})

@app.route('/api/vehicle-detections/<int:detection_id>', methods=['DELETE'])
@login_required
def api_vehicle_detection_delete(detection_id):
    if current_user.role != 'admin':
        return jsonify({'status': 'error', 'message': 'Admin access required'}), 403
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM vehicle_detections WHERE id = ?', (detection_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted'})

@app.route('/plate_frames/<path:filename>')
def serve_plate_frames(filename):
    return send_from_directory('plate_frames', filename)

@app.route('/api/report', methods=['GET'])
@login_required
def api_report():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM accidents ORDER BY timestamp DESC LIMIT 50')
    accidents = [dict(row) for row in c.fetchall()]
    c.execute('SELECT avg(confidence) as avg_conf FROM accidents')
    avg_conf = c.fetchone()['avg_conf'] or 0
    c.execute('SELECT count(*) as total FROM accidents')
    total = c.fetchone()['total'] or 0
    c.execute('SELECT severity, count(*) as count FROM accidents GROUP BY severity')
    severity_rows = c.fetchall()
    severity_data = {row['severity']: row['count'] for row in severity_rows}
    c.execute('SELECT status, count(*) as count FROM accidents GROUP BY status')
    status_rows = c.fetchall()
    status_data = {row['status']: row['count'] for row in status_rows}
    conn.close()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("AI Accident Detection Report", styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Generated: {datetime.now().isoformat()}", styles['Normal']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Total Accidents: {total}", styles['Heading2']))
    elements.append(Paragraph(f"Average Confidence: {avg_conf:.2f}", styles['Normal']))
    elements.append(Spacer(1, 12))
    if severity_data:
        elements.append(Paragraph("Severity Breakdown", styles['Heading3']))
        sev_rows = [['Severity', 'Count']]
        for sev, count in severity_data.items():
            sev_rows.append([sev.title(), str(count)])
        sev_table = Table(sev_rows)
        sev_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(sev_table)
        elements.append(Spacer(1, 12))
    if status_data:
        elements.append(Paragraph("Status Breakdown", styles['Heading3']))
        stat_rows = [['Status', 'Count']]
        for stat, count in status_data.items():
            stat_rows.append([stat.replace('_', ' ').title(), str(count)])
        stat_table = Table(stat_rows)
        stat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(stat_table)
        elements.append(Spacer(1, 12))
    if accidents:
        elements.append(Paragraph("Recent Accidents", styles['Heading3']))
        data = [['Frame', 'Timestamp', 'Type', 'Severity', 'Status', 'Confidence']]
        for acc in accidents[:20]:
            data.append([str(acc.get('frame_number', '')), acc.get('timestamp', ''), acc.get('vehicle_type', ''),
                         acc.get('severity', '').title(), acc.get('status', '').replace('_', ' ').title(), str(round(acc.get('confidence', 0), 2))])
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='accident_report.pdf', mimetype='application/pdf')

@app.route('/api/notifications/test', methods=['POST'])
@login_required
def api_test_notification():
    if current_user.role != 'admin':
        return jsonify({'status': 'error', 'message': 'Admin access required'}), 403
    data = request.json
    results = {}
    if data.get('telegram'):
        notifier = TelegramNotifier(BOT_TOKEN, CHAT_ID)
        notifier.send_emergency_alert([{'type': 'test', 'confidence': 0.99}])
        results['telegram'] = 'sent'
    if data.get('email'):
        email_result, email_msg = email_notifier.send_alert(data.get('email'), 'Test Alert', 'This is a test email from AI Accident Detection Dashboard')
        results['email'] = 'sent' if email_result else 'failed'
        if not email_result:
            results['email_error'] = email_msg
    if data.get('sms'):
        sms_result = sms_notifier.send_alert(data.get('sms'), 'Test SMS from AI Accident Detection Dashboard')
        results['sms'] = 'sent' if sms_result else 'failed'
    if data.get('whatsapp'):
        wa_result = whatsapp_notifier.send_alert(data.get('whatsapp'), 'Test WhatsApp from AI Accident Detection Dashboard')
        results['whatsapp'] = 'sent' if wa_result else 'failed'
    return jsonify({'status': 'sent', 'results': results})

@app.route('/api/login', methods=['POST'])
def api_login():
    username = request.json.get('username')
    password = request.json.get('password')
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
    row = c.fetchone()
    conn.close()
    if row:
        user = User(row['id'], row['username'], row['role'], row['email'], row['phone'])
        login_user(user)
        return jsonify({'status': 'success', 'role': user.role})
    return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({'status': 'logged_out'})

@app.route('/api/user', methods=['GET'])
@login_required
def api_current_user():
    return jsonify({'username': current_user.username, 'role': current_user.role})

@app.route('/api/video/queue', methods=['GET', 'POST'])
@login_required
def api_video_queue():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'GET':
        c.execute('SELECT * FROM video_queue ORDER BY created_at DESC')
        queue = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(queue)
    elif request.method == 'POST':
        data = request.json
        c.execute('INSERT INTO video_queue (video_path, source_type, priority) VALUES (?, ?, ?)',
                  (data.get('video_path'), data.get('source_type'), data.get('priority', 0)))
        conn.commit()
        conn.close()
        return jsonify({'status': 'queued'}), 201

@app.route('/api/video/queue/<int:queue_id>', methods=['DELETE'])
@login_required
def api_video_queue_delete(queue_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM video_queue WHERE id = ?', (queue_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted'})

@app.route('/api/hospitals/nearby', methods=['GET'])
@login_required
def api_nearby_hospitals():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', default=5000, type=int)
    if lat is None or lng is None:
        return jsonify({'status': 'error', 'message': 'lat and lng are required'}), 400
    try:
        overpass_url = 'https://overpass-api.de/api/interpreter'
        query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:{radius},{lat},{lng});
          way["amenity"="hospital"](around:{radius},{lat},{lng});
          relation["amenity"="hospital"](around:{radius},{lat},{lng});
          node["healthcare"="hospital"](around:{radius},{lat},{lng});
          way["healthcare"="hospital"](around:{radius},{lat},{lng});
          node["amenity"="clinic"](around:{radius},{lat},{lng});
          way["amenity"="clinic"](around:{radius},{lat},{lng});
          node["healthcare"="clinic"](around:{radius},{lat},{lng});
          way["healthcare"="clinic"](around:{radius},{lat},{lng});
        );
        out center;
        """
        headers = {'Accept': 'application/json', 'User-Agent': 'AI-Accident-Detection/1.0'}
        resp = requests.post(overpass_url, data={'data': query}, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        seen = set()
        hospitals = []
        for el in data.get('elements', []):
            tags = el.get('tags', {})
            el_lat = el.get('lat') or (el.get('center') or {}).get('lat')
            el_lng = el.get('lon') or (el.get('center') or {}).get('lon')
            name = (tags.get('name') or '').strip()
            if not name or el_lat is None or el_lng is None:
                continue
            key = (name.lower(), round(float(el_lat), 4), round(float(el_lng), 4))
            if key in seen:
                continue
            seen.add(key)
            amenity = tags.get('amenity', tags.get('healthcare', 'hospital'))
            is_hospital = amenity in ('hospital',) or tags.get('healthcare') == 'hospital'
            addr_parts = [tags.get('addr:street', ''), tags.get('addr:city', ''), tags.get('addr:full', '')]
            address = ', '.join([a for a in addr_parts if a]) or tags.get('addr:suburb', '')
            distance = round(((float(el_lat) - lat) ** 2 + (float(el_lng) - lng) ** 2) ** 0.5 * 111000)
            hospitals.append({
                'name': name,
                'lat': float(el_lat),
                'lng': float(el_lng),
                'type': 'Hospital' if is_hospital else 'Clinic',
                'phone': tags.get('phone', '') or tags.get('contact:phone', ''),
                'address': address,
                'distance_m': distance
            })
        hospitals.sort(key=lambda h: (0 if h['type'] == 'Hospital' else 1, h['distance_m']))
        hospitals = hospitals[:25]
        return jsonify({'status': 'success', 'hospitals': hospitals})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/output/<path:filename>')
def serve_output(filename):
    return send_from_directory('output', filename)

@app.route('/accident_frames/<path:filename>')
def serve_accident_frames(filename):
    return send_from_directory('accident_frames', filename)

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory('uploads', filename)

# ---------------- STARTUP ----------------
start_queue_processor()

print("=" * 60)
print("AI Accident Detection System - Starting Up")
print("=" * 60)
print(f"[STARTUP] Base directory: {BASE_DIR}")
print(f"[STARTUP] Data directory: {DATA_DIR}")
print(f"[STARTUP] Model path: {MODEL_PATH}")
print(f"[STARTUP] Model exists: {os.path.exists(MODEL_PATH)}")
print(f"[STARTUP] YOLO loaded: {yolo_model is not None}")
print(f"[STARTUP] Roboflow loaded: {crash_model is not None}")
print(f"[STARTUP] Database: {DB_PATH}")
print(f"[STARTUP] Telegram configured: {bool(BOT_TOKEN and CHAT_ID)}")
print(f"[STARTUP] Output directory: {OUTPUT_DIR}")
print(f"[STARTUP] Upload directory: {UPLOAD_DIR}")
print(f"[STARTUP] Accident frames directory: {SAVE_DIR}")
print(f"[STARTUP] YouTube support: {'yt-dlp installed' if YTDLP_AVAILABLE else 'yt-dlp NOT installed'}")
print("=" * 60)

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    print(f"[STARTUP] Starting Flask dev server on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)