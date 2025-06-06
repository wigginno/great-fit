# syntax=docker/dockerfile:1
FROM node:20-slim AS assets
ARG TARGETARCH
WORKDIR /work

RUN apt-get update && apt-get install -y curl ca-certificates && rm -rf /var/lib/apt/lists/*

RUN if [ "$TARGETARCH" = "amd64" ]; then TAIL_ARCH=x64; \
    elif [ "$TARGETARCH" = "arm64" ]; then TAIL_ARCH=arm64; \
    else echo "unsupported arch $TARGETARCH" && exit 1; fi && \
    curl -fsSL -o /usr/local/bin/tailwindcss \
      "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-${TAIL_ARCH}" && \
    chmod +x /usr/local/bin/tailwindcss

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

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
