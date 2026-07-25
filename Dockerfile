FROM python:3.11-slim

WORKDIR /app

# 依赖层（缓存友好）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY main.py ./
COPY agent/ agent/
COPY config/ config/
COPY routes/ routes/
COPY knowledge/ knowledge/
COPY web/ web/
COPY db.py auth.py ./

# 不 COPY: .env, .git, __pycache__, *.db, tests/

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
