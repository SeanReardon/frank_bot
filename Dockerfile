# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Configure environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_FILE=~/logs/frank_bot-api.log \
    PORT=8000 \
    HOST=0.0.0.0

# Copy requirements first for better caching
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port for HTTP transport
EXPOSE 8000

# Run the MCP server
CMD ["python", "app.py"]

