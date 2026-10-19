FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-cloud.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt && useradd --uid 10001 --create-home reason
COPY reason reason
COPY web web
COPY cloud-web cloud-web
USER reason
EXPOSE 8080
CMD ["sh","-c","exec python -m uvicorn reason.cloud:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
