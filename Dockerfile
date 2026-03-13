# Use slightly older but more stable lightweight image to avoid compiling packages from source
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies strictly without caching
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project code
COPY . .

# Expose port 10000 (Render.com default)
EXPOSE 10000

# Run Uvicorn strictly with 1 worker to stay within Render's 512MB RAM limit
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000", "--workers", "1"]