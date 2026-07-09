# Portable container — works on Hugging Face Spaces (Docker SDK), Fly.io,
# Google Cloud Run, Railway, etc. Hugging Face expects the app on port 7860.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces uses 7860; other hosts inject their own $PORT.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn verdikt.server:app --host 0.0.0.0 --port ${PORT:-7860}"]
