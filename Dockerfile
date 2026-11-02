# Use a small, production-appropriate base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment port and expose it
ENV PORT=8080
EXPOSE $PORT

# Start command binding to 0.0.0.0 and the configured port
CMD gunicorn --bind 0.0.0.0:$PORT app:app