# Build stage
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa /uv /uvx /bin/

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
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

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
    DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings.production \
    DJANGO_ENV=production

# Expose port
EXPOSE 8000

# Switch to non-root user
USER django

# Command to run the application
CMD ["gunicorn", "DjangoApiStarter.wsgi:application", "-c", "gunicorn.conf.py"]
