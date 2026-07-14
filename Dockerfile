# Build stage
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install the locked runtime environment.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Final stage
FROM python:3.14-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
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

# Collect immutable static assets while building the image.
RUN DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings.test \
    python manage.py collectstatic --noinput

# Set permissions
RUN chown -R django:django /app

# Ensure staticfiles directory exists and is owned by django user
RUN mkdir -p /app/staticfiles && chown -R django:django /app/staticfiles

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings.development \
    DJANGO_ENV=development

# Expose port
EXPOSE 8000

# Switch to non-root user
USER django

# Command to run the application
CMD ["sh", "-c", "python manage.py collectstatic --noinput && if [ \"$DJANGO_ENV\" = \"production\" ]; then gunicorn DjangoApiStarter.wsgi:application -c gunicorn.conf.py; else python manage.py runserver 0.0.0.0:8000; fi"]
