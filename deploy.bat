@echo off
REM =====================================================
REM  EcoStory Backend - Cloud Run Deploy Script
REM  Run this from: c:\python_project\ecostory_backend
REM =====================================================

gcloud run deploy ecostory-backend ^
  --source . ^
  --platform managed ^
  --region us-central1 ^
  --allow-unauthenticated ^
  --port 8080 ^
  --memory 1Gi ^
  --cpu 1 ^
  --min-instances 1 ^
  --max-instances 10 ^
  --set-env-vars="GOOGLE_CLOUD_PROJECT=ecostory-b31b6" ^
  --set-secrets="OPENAI_API_KEY=OPENAI_API_KEY:latest,INTERNAL_API_KEY=INTERNAL_API_KEY:latest,PINECONE_API_KEY=PINECONE_API_KEY:latest,PINECONE_ENV=PINECONE_ENV:latest,KABIR_INDEX_NAME=KABIR_INDEX_NAME:latest,PINECONE_INDEX_NAME=PINECONE_INDEX_NAME:latest,PINECONE_INDEX_NAME2=PINECONE_INDEX_NAME2:latest,PINECONE_INDEX_NAME3=PINECONE_INDEX_NAME3:latest,KABIR_INDEX_HOST=KABIR_INDEX_HOST:latest,PINECONE_INDEX_HOST=PINECONE_INDEX_HOST:latest,PINECONE_INDEX_HOST2=PINECONE_INDEX_HOST2:latest,PINECONE_INDEX_HOST3=PINECONE_INDEX_HOST3:latest"
