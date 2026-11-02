FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser && mkdir /data && chown appuser:appuser /data
COPY --chown=appuser:appuser app ./app
USER appuser
ENV DATABASE_URL=sqlite:////data/annotations.db TOKEN_TTL_HOURS=24
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
