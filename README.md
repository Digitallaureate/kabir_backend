# EcoStory Backend API

A robust FastAPI backend for the EcoStory platform, featuring Firebase Authentication, Pinecone vector search, and OpenAI-powered intent detection for historical exploration.

## 🚀 Features

- **Standardized API Interface**: Unified `msg` / `metadata` structure with `request_id` for every response.
- **Global Firebase Security**: Default protection for all endpoints with intelligent public path whitelisting.
- **Development Bypass**: Secure local debugging mode to skip token verification while maintaining project-id safety.
- **Micro-service Modules**: Modular design for Historical Sites, FCM Notifications, and Text Processing.
- **Searchable Knowledge**: Vector search integration using Pinecone for intelligent data retrieval.

## 🛠 Technology Stack

- **Framework**: FastAPI (Python)
- **Database**: Google Cloud Firestore & Pinecone (Vector Search)
- **Authentication**: Firebase Admin SDK
- **AI/LLM**: OpenAI GPT Models
- **Deployment**: Google Cloud Run (Containerized with Docker)

## 📋 Prerequisites

- Python 3.9+
- Google Cloud Platform Account
- Firebase Project
- Pinecone API Key
- OpenAI API Key

## ⚙️ Installation & Setup

1. **Clone the repository**:
   ```powershell
   git clone <repository-url>
   cd ecostory_backend
   ```

2. **Create a Virtual Environment**:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

4. **Firebase Configuration**:
   Place your Firebase service account JSON file in the root directory and name it `firebase-service-account.json`.

5. **Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json
   OPENAI_API_KEY=your_openai_key
   PINECONE_API_KEY=your_pinecone_key
   PINECONE_ENV=your_pinecone_region
   KABIR_INDEX_NAME=your_index_name
   
   # Development Only
   DEBUG_SKIP_VERIFY=true
   ```

## 🔐 Authentication & Security

### Global Middleware
The backend uses `FirebaseAuthMiddleware` to protect all routes. 
- **Production**: Strictly verifies Firebase ID Tokens using Google's public keys.
- **Development**: If `DEBUG_SKIP_VERIFY=true` is set, the backend skips signature checks but still validates that the token belongs to the correct Firebase project.

### Response Structure
All responses follow this unified JSON format:
```json
{
  "msg": { "data": "here" },
  "metadata": {
    "request_id": "uuid-generated-per-call",
    "success": true
  }
}
```

## 🛠 Running Locally

```powershell
uvicorn src.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.
Documentation is available at `http://127.0.0.1:8000/docs`.

## ☁️ Deployment (Google Cloud Run)

To deploy to Google Cloud Run, use the following template:

gcloud run deploy ecostory-backend --source . --platform managed --region us-central1 --allow-unauthenticated --port 8080 --memory 1Gi --cpu 1 --min-instances 1 --max-instances 10 --set-env-vars="GOOGLE_CLOUD_PROJECT=ecostory-b31b6"

```powershell
gcloud run deploy ecostory-backend `
  --source . `
  --platform managed `
  --region us-central1 `
  --allow-unauthenticated `
  --port 8080 `
  --set-env-vars="FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json,OPENAI_API_KEY=...,PINECONE_API_KEY=..."
```

## 📂 Project Structure

```text
src/
├── core/             # Core infrastructure (middleware, schemas, error handlers)
├── database/         # Database connectors (Firestore, Pinecone)
├── modules/          # Business logic modules
│   ├── historical_site/
│   ├── fcm/
│   └── process_text/
└── main.py           # Application entry point
```

to check in which project it is deployed

(.venv) PS C:\python_project\ecostory_backend> gcloud config get-value project
[EMAIL_ADDRESS]

(.venv) PS C:\python_project\ecostory_backend> 
