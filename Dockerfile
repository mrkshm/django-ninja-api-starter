# Build stage
FROM python:3.13 as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.13

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN groupadd -r django && useradd -r -g django django

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Set permissions
RUN chown -R django:django /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings \
    DJANGO_ENV=development

# Expose port
EXPOSE 8000

# Switch to non-root user
USER django

# Command to run the application
CMD ["sh", "-c", "if [ \"$DJANGO_ENV\" = \"production\" ]; then gunicorn DjangoApiStarter.wsgi:application -c gunicorn.conf.py; else python manage.py runserver 0.0.0.0:8000; fi"]
