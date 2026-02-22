# Use lightweight Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (if needed for some packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project code
COPY . .

# Expose port 10000 (Render.com default)
EXPOSE 10000

# Run Uvicorn on port 10000 and host 0.0.0.0
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
