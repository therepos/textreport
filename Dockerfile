FROM python:3.11-slim

WORKDIR /app

# (Optional but useful) system deps for pdfplumber
RUN apt-get update && apt-get install -y build-essential gcc libjpeg62-turbo-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8090
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
