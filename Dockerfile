# Use Python 3.11 slim image with latest security patches
FROM python:3.11.8-slim

# Set working directory
WORKDIR /app

# Install system security updates and essential tools
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1000 app

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install dependencies securely
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code and set proper ownership
COPY --chown=app:app . .

# Switch to non-root user for security
USER app

# Expose port 8080 (Cloud Run default)
EXPOSE 8080

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Add health check for better monitoring (simplified for Cloud Run)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]