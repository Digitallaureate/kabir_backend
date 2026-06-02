# 🏰 EcoStory Backend API

A professional, modular FastAPI backend designed for the EcoStory platform. This project follows **Senior Architect** best practices, featuring type-safe configuration, secure secret management, and a highly scalable service module system.

---

## 🚀 Key Architectural Features

- **Standardized API Interface**: Unified `msg` / `metadata` structure with `request_id` for every response.
- **Type-Safe Configuration**: Centralized settings management using **Pydantic Settings**.
- **Professional Secret Management**: Zero-secret code and scripts using **Google Cloud Secret Manager**.
- **Modular Design**: Completely decoupled modules for Services, Historical Sites, FCM, and Text Processing.
- **Dynamic Service Engine**: File-based dynamic form and service listing configuration for easy updates.

---

## 🛠 Technology Stack

- **Framework**: FastAPI (Python 3.13+)
- **Database**: Google Cloud Firestore & Pinecone (Vector Search)
- **Security**: Firebase Admin SDK & Google Secret Manager
- **AI/LLM**: OpenAI GPT Models
- **Infrastucture**: Google Cloud Run (Containerized)

---

## 📋 Local Development Setup

### 1. Prerequisites
- Python 3.13+
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (Logged in with `gcloud auth login`)
- A Firebase Service Account JSON file.

### 2. Installation
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Local Configuration
Create a `.env` file in the root directory:
```env
DEBUG=true
DEBUG_SKIP_VERIFY=true  # Allows browser/Postman testing without heavy auth headers
GOOGLE_CLOUD_PROJECT=ecostory-b31b6
FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json

# Local API Keys (for local testing only)
OPENAI_API_KEY=sk-xxxx...
PINECONE_API_KEY=pcsk_xxxx...
...

```

for deploying new api key
echo -n "YOUR_NEW_OPENAI_KEY" | gcloud secrets versions add OPENAI_API_KEY --data-file=-

$secret = "YOUR_NEW_OPENAI_KEY"
$secret | gcloud secrets versions add OPENAI_API_KEY --data-file=-

### 4. Running Locally
```powershell
uvicorn src.main:app --reload
```
- **API URL**: `http://127.0.0.1:8000/api`
- **Docs (Swagger)**: `http://127.0.0.1:8000/docs`

---

## ☁️ Production Deployment

### 🏛️ The "Architect" Pattern
This project uses **Google Cloud Secret Manager**. All sensitive keys are stored in the cloud, NOT in the code or deployment scripts.

### 🚀 Deploying to Cloud Run
To deploy the latest code to production, simply run the deployment script:
```powershell
.\deploy.bat
```
*Note: This script automatically handles project mapping, memory allocation, and secret injection.*

---

## 🧩 Adding New Services & Forms
The `services` module is dynamic. You can add new content without changing a single line of Python code.

1.  **Add to Service List**: Modify [src/modules/services/data/services.json](file:///c:/python_project/ecostory_backend/src/modules/services/data/services.json).
2.  **Add a Form**: Create a new JSON file in [src/modules/services/data/forms/](file:///c:/python_project/ecostory_backend/src/modules/services/data/forms/) (e.g., `new_service.json`).
3.  **Deploy**: Run `.\deploy.bat`.

---

## 📂 Project Structure

```text
src/
├── config/           # Type-safe Pydantic Settings
├── core/             # Infrastructure (Auth Middleware, API Registry)
├── database/         # Firebase & Firestore Connectors
├── modules/          # Business Logic
│   ├── services/     # Dynamic Services & Form Engine [NEW]
│   ├── historical_site/
│   ├── fcm/
│   └── process_text/
└── main.py           # Entry Point & App Lifecycle
```

---

## 🔐 Security Notes
- **Production Auth**: Strictly verifies Firebase ID tokens.
- **Local Auth**: If `DEBUG_SKIP_VERIFY` is enabled, any string in the Bearer token works, but the backend still ensures the token is for the correct project.
- **Git Safety**: `.env` and `deploy.bat` (if it contains secrets) are excluded via `.gitignore`.
