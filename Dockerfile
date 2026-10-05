FROM python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/kindle-hub
RUN apk add --no-cache font-dejavu tzdata
COPY requirements.lock ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.lock
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir --no-deps . \
    && addgroup -S appuser && adduser -S -D -H -u 10001 -G appuser appuser \
    && mkdir -p /data /cache && chown -R appuser:appuser /data /cache
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
