# syntax=docker/dockerfile:1
ARG TARGETARCH=amd64
FROM node:20-slim AS assets
WORKDIR /work

ADD https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-${TARGETARCH} \
    /usr/local/bin/tailwindcss
RUN chmod +x /usr/local/bin/tailwindcss

COPY src/index.css src/index.css
RUN tailwindcss -i src/index.css -o build/tailwind.css --minify

FROM python:3.11-slim

# system libs for psycopg2 and TLS
RUN apt-get update && apt-get install -y \
        build-essential libpq-dev ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy source and pre-built CSS
COPY --from=assets /work/build/tailwind.css static/css/
COPY . .

# bind to the port App Runner injects via $PORT (default 8080)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$PORT"]
