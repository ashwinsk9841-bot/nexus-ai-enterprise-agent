FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXUS_NO_BROWSER=1

WORKDIR /srv/nexus

# Node.js is required only for the one-time frontend production build
# (FastAPI serves the finished dist/ afterward).
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY app.py ./

# One-time frontend build so the container serves a ready-made dist/.
RUN cd frontend && npm install && npm run build

RUN chmod -R a+r .

EXPOSE 8000

# Single process: FastAPI serves both the API and the built frontend.
CMD ["python", "app.py"]