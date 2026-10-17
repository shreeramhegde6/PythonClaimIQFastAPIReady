FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY scripts ./scripts
COPY infra ./infra
ENV PYTHONPATH=/app/src
CMD ["uvicorn","claimiq.main:app","--host","0.0.0.0","--port","8000"]
