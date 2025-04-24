FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Install Node and Tailwind CLI
RUN apt-get update && apt-get install -y nodejs npm \
    && npm install -g tailwindcss @tailwindcss/cli

# Copy app source and build assets
COPY . .
RUN npm install tailwindcss@latest && \
    npx tailwindcss -i src/index.css -o static/css/tailwind.css --minify
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]