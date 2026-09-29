# 🚨 AI Accident Detection System

An AI-powered road safety and accident detection platform that analyzes CCTV/video footage, detects vehicles and potential accidents, records incident evidence, and supports real-time emergency notifications through a web dashboard.

## 📌 Overview

This project combines **YOLOv8**, **OpenCV**, **Roboflow**, **Flask**, **SQLite**, and notification services to build an end-to-end accident monitoring system.

The application can:

- 🎥 Process uploaded road/CCTV video footage
- 🚗 Detect vehicles such as cars, trucks, buses, and motorcycles
- 🧭 Track detected vehicles across video frames
- 💥 Analyze potential collisions using vehicle overlap/IoU and crash-model inference
- 🧠 Use a Roboflow crash-detection model for additional accident confirmation
- 📸 Save accident frames and generated evidence
- 🎬 Save accident video clips
- 📊 Maintain accident and vehicle information through the dashboard/database
- 🚘 Support license-plate detection/OCR workflows
- 📱 Send accident alerts through Telegram
- 📧 Support email notifications
- 📲 Support SMS/WhatsApp notification configuration through Twilio
- 🌐 Provide a Flask-based web dashboard and API
- 🐳 Support Docker-based deployment
- ☁️ Include deployment configuration for services such as Render

> **Note:** This project is intended as a prototype/research and demonstration system. Detection results depend on camera quality, model performance, lighting, traffic conditions, and configuration thresholds.

---

## 🏗️ System Architecture

```text
                    ┌──────────────────────┐
                    │   CCTV / Video Input │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      OpenCV           │
                    │  Frame Processing     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       YOLOv8         │
                    │  Vehicle Detection   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Vehicle Tracking     │
                    │ + IoU Analysis       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Roboflow Crash Model │
                    │ Accident Confirmation│
                    └──────────┬───────────┘
                               │
                         Accident?
                         /       \
                       No         Yes
                       │           │
                       ▼           ▼
                  Continue     ┌───────────────┐
                               │ Save Evidence │
                               │ Frame + Clip  │
                               └───────┬───────┘
                                       │
                         ┌─────────────┼─────────────┐
                         ▼             ▼             ▼
                    SQLite DB     Dashboard     Notifications
                                      │        Telegram / Email /
                                      │        SMS / WhatsApp
                                      ▼
                                Operator Response
```

---

## ✨ Key Features

### 1. AI Vehicle Detection
Uses **YOLOv8** to identify road vehicles from video frames.

Supported vehicle categories include:

- Car
- Truck
- Bus
- Motorcycle

### 2. Vehicle Tracking
Detected vehicles are tracked across frames so that the system can maintain vehicle identities during video processing.

### 3. Accident Detection
The detection pipeline combines vehicle movement/overlap analysis with a crash-detection model.

The configured pipeline includes:

```text
Vehicle Detection
       ↓
Vehicle Tracking
       ↓
IoU / Collision Analysis
       ↓
Crash Model Confirmation
       ↓
Accident Event
```

### 4. Accident Evidence
When an accident is detected, the system can store:

- Accident frame
- Detection confidence
- Accident type
- Severity
- Frame number
- Camera/location information
- Accident video clip

### 5. Real-Time Alerts

The project contains notification support for:

- Telegram
- Email
- SMS
- WhatsApp

Notification channels are configured through environment variables/settings.

### 6. License Plate Recognition

The application contains a license-plate processing module with support for OCR engines such as:

- Tesseract
- EasyOCR

The available OCR engine is selected based on the installed dependencies.

### 7. Web Dashboard

The backend is built using **Flask** and serves the web interface from the `website/` directory.

The application also exposes API endpoints for dashboard operations, status checks, authentication, detection processing, and system data.

### 8. Database

The application uses **SQLite** for local persistence, including dashboard/system information and detection-related records.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core programming language |
| YOLOv8 / Ultralytics | Vehicle detection |
| OpenCV | Video and image processing |
| Roboflow | Crash-detection model inference |
| Flask | Backend web application/API |
| Flask-CORS | Cross-origin API support |
| Flask-Login | Authentication |
| SQLite | Database |
| Telegram Bot API | Accident alerts |
| Twilio | SMS/WhatsApp integration |
| Tesseract / EasyOCR | License-plate OCR |
| Docker | Containerized deployment |
| Gunicorn | Production WSGI server |
| Render | Cloud deployment option |

The current repository's dependency file includes Ultralytics, OpenCV, NumPy, Roboflow, Flask, Flask-CORS, Flask-Login, Gunicorn, Twilio, Telegram tooling, ReportLab, and yt-dlp. 

---

## 📂 Project Structure

```text
AI-accident-detection/
│
├── accident_frames/          # Saved accident evidence frames
├── plate_frames/             # License-plate related frames
├── website/                  # Frontend/dashboard files
│
├── app.py                    # Main Flask application
├── accident detection.py     # Accident detection script
├── bot.py                    # Telegram bot functionality
├── get_chat_id.py            # Telegram chat ID helper
│
├── accident_dashboard.db     # SQLite database
│
├── yolov8n.pt                # YOLOv8 Nano model
├── yolov8s.pt                # YOLOv8 Small model
│
├── .env.example              # Environment-variable template
├── .gitignore
├── .dockerignore
├── Dockerfile
├── render.yaml               # Render deployment configuration
├── DEPLOYMENT.md              # Deployment instructions
├── requirements.txt
└── README.md
```

---

## ⚙️ Requirements

Before running the project, install:

- Python 3.9+
- pip
- Git
- Optional: Docker
- Optional: Tesseract OCR for license-plate recognition
- Optional: Telegram Bot credentials
- Optional: Roboflow API credentials
- Optional: Twilio credentials for SMS/WhatsApp

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/Dhiren-9974/AI-accident-detection.git
cd AI-accident-detection
```

### 2. Create a virtual environment

#### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 🔐 Environment Configuration

Create a `.env` file in the project root.

```env
SECRET_KEY=your_secret_key

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

ROBOFLOW_API_KEY=your_roboflow_api_key
ROBOFLOW_WORKSPACE=your_workspace
ROBOFLOW_PROJECT=your_project

SMTP_HOST=smtp.example.com
SMTP_USER=your_email
SMTP_PASSWORD=your_password
FROM_EMAIL=your_email

TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_PHONE=your_phone
TWILIO_FROM_WHATSAPP=your_whatsapp_sender
```

### ⚠️ Security

**Never commit your real `.env` file, API keys, bot tokens, passwords, or secret keys to GitHub.**

Use `.env.example` as the template for required variables.

---

## ▶️ Run the Application

Start the Flask application:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

The application also provides a health endpoint:

```text
http://127.0.0.1:5000/health
```

---

## 🎥 Accident Detection Workflow

```text
1. Upload / provide video
          ↓
2. Extract video frames
          ↓
3. YOLOv8 detects vehicles
          ↓
4. Track vehicles between frames
          ↓
5. Calculate vehicle overlap / IoU
          ↓
6. Analyze possible collision
          ↓
7. Roboflow crash model confirms accident
          ↓
8. Estimate accident severity
          ↓
9. Save accident frame
          ↓
10. Save accident clip
          ↓
11. Store event information
          ↓
12. Send emergency notification
          ↓
13. Display event on dashboard
```

---

## 📊 Detection Logic

The system uses configurable parameters for the detection pipeline, including:

```text
Confidence Threshold
Crash Confidence Threshold
IoU Match Threshold
Frame Processing Interval
Maximum Lost Frames
Notification Cooldown
```

These parameters can be adjusted according to the camera environment and model performance.

---

## 🚨 Alert System

When an accident event is detected, the system can prepare an alert containing information such as:

```text
ACCIDENT ALERT

Time
Camera / Location
Frame Number
Number of Detected Incidents
Accident Type
Severity
Confidence
```

Telegram notifications include a cooldown mechanism to reduce repeated alerts for the same detection period.

---

## 🐳 Docker

Build the Docker image:

```bash
docker build -t ai-accident-detection .
```

Run the container:

```bash
docker run -p 5000:5000 --env-file .env ai-accident-detection
```

Then open:

```text
http://localhost:5000
```

---

## ☁️ Deployment

The repository contains:

- `Dockerfile`
- `render.yaml`
- `DEPLOYMENT.md`

These files support deployment to cloud platforms such as **Render** and other Docker-compatible environments.

For production deployment, configure the required environment variables securely in the hosting platform rather than committing them to the repository.

See:

```text
DEPLOYMENT.md
```

for the project's deployment instructions.

---

## 🔌 API / Backend

The Flask application provides backend API functionality for:

- Authentication
- Health/status checks
- Video processing
- Accident events
- Dashboard information
- Settings
- Notifications
- Detection results

The frontend communicates with the Flask backend through API endpoints.

---

## 🧪 Testing & Verification

After installation, verify the environment:

```bash
python --version
pip --version
```

Then start the application:

```bash
python app.py
```

Check:

```text
http://127.0.0.1:5000/health
```

A successful health response should indicate that the application is running.

---

## 📈 Future Improvements

Potential future improvements include:

- Live RTSP/IP camera integration
- Multi-camera monitoring
- More advanced multi-object tracking
- Improved false-positive filtering
- Accident severity classification improvements
- GPS-based incident location
- Emergency-service integration
- Cloud-scale event processing
- PostgreSQL/Redis-based production architecture
- Advanced analytics and historical reports
- Role-based operator management
- Improved license-plate recognition accuracy
- Mobile application integration

---

## ⚠️ Limitations

This is an AI-assisted detection system and should not be treated as a guaranteed accident-detection or emergency-dispatch system.

Performance may be affected by:

- Low-resolution CCTV footage
- Poor lighting
- Camera angle
- Heavy traffic
- Occlusion
- Weather conditions
- Model confidence thresholds
- Incorrect or incomplete training data
- False positives / false negatives

Human verification should be used for critical operational decisions.

---

## 👨‍💻 Author

**Dhirendra Nogiya**

GitHub:  
https://github.com/Dhiren-9974

Project Repository:  
https://github.com/Dhiren-9974/AI-accident-detection

---

## 📄 License

See the repository's license information and project files for applicable licensing terms.

---

## ⭐ Project

If you find this project useful for learning or research, consider giving the repository a ⭐ on GitHub.

**AI Accident Detection System — Using AI & Computer Vision for Smarter Road Safety.**
