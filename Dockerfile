# EvolvingClass API service (Flask + service layer).
# Mirrors the dev run: same source layout on PYTHONPATH, third-party
# floors taken from database/pipeline/service/web pyproject manifests.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/database:/app/pipeline:/app/service:/app/web \
    PORT=5001 \
    HOST=0.0.0.0

WORKDIR /app

RUN pip install --no-cache-dir \
    "sqlalchemy>=2.0" \
    "alembic>=1.13" \
    "psycopg[binary]>=3.1" \
    "python-dotenv>=1.0" \
    "flask>=3.0"

COPY database/ ./database/
COPY pipeline/ ./pipeline/
COPY service/ ./service/
COPY web/ ./web/

EXPOSE 5001

# Seed demo data (idempotent), then serve.
CMD ["sh", "-c", "python -m evolvingclass_web.seed && python -m evolvingclass_web.app"]
