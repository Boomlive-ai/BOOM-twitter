# Use an official lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Expose port (FastAPI default)
EXPOSE 8000

# Start Uvicorn with the correct module name
CMD ["uvicorn", "twitter_bot_polling:app", "--host", "0.0.0.0", "--port", "8000"]
