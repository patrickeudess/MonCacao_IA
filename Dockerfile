FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MONCACAO_HOST=0.0.0.0 \
    MONCACAO_DATABASE=/data/v1.sqlite \
    MONCACAO_HTTPS=1 \
    PORT=5000
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api_server.py v1.py ./
COPY templates ./templates
COPY static ./static
RUN mkdir -p /data
EXPOSE 5000
CMD ["python", "api_server.py"]
