# Docker Setup Guide

This document explains the Docker configuration for the Django Ninja API project and the required environment setup.

## Docker Configuration

The project uses a multi-container setup with Docker Compose, consisting of:
- Django application container
- PostgreSQL database container with PostGIS
- Redis container
- Celery worker container
- Celery beat container

### Container Details

#### Django Application (`web`)
- Base image: Python 3.13
- Port: 8000
- Multi-stage build for optimized image size
- Virtual environment for dependency isolation
- Runs as non-root user for security

#### PostgreSQL Database (`db`)
- Image: postgis/postgis:15-3.3-alpine
- Port: 5432
- Persistent volume for data storage
- PostGIS extension enabled
- Health check configured

#### Redis (`redis`)
- Image: redis:7-alpine
- Port: 6379
- Persistent volume for data storage

#### Celery Worker (`celery_worker`)
- Same base image as web service
- Runs as non-root user
- Connected to Redis for task queue
- Pre-configured concurrency settings

#### Celery Beat (`celery_beat`)
- Same base image as web service
- Runs as non-root user
- Uses database scheduler
- Waits for migrations before starting

## Environment Variables

### Required Environment Variables

The following environment variables must be set in your Django settings:

```python
# Database Configuration
POSTGRES_DB=django_db
POSTGRES_USER=django_user
POSTGRES_PASSWORD=django_pass
POSTGRES_HOST=db  # Docker service name
POSTGRES_PORT=5432

# Redis Configuration
REDIS_URL=redis://redis:6379/1  # Docker service name

# Django Settings
DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings
```

### Optional Environment Variables

```python
# Security
SECRET_KEY=your-secret-key-here
DEBUG=True/False

# Allowed Hosts
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Frontend URL
FRONTEND_URL=http://localhost:3000
```

## Project Setup

1. Create a `.env` file in your project root with the required environment variables:

```bash
# Database
POSTGRES_DB=django_db
POSTGRES_USER=django_user
POSTGRES_PASSWORD=django_pass
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/1

# Django
DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings
SECRET_KEY=your-secret-key-here
DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
FRONTEND_URL=http://localhost:3000
```

2. Update your Django settings (`settings.py`) to use environment variables:

```python
import os
from pathlib import Path

# Database settings
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ.get('POSTGRES_DB'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': os.environ.get('POSTGRES_HOST'),
        'PORT': os.environ.get('POSTGRES_PORT'),
    }
}

# Redis settings
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get('REDIS_URL'),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

# Celery settings
CELERY_BROKER_URL = os.environ.get('REDIS_URL')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL')
```

## Running the Project

1. Build and start all containers:
```bash
docker-compose up --build
```

This will:
- Start the PostgreSQL database with PostGIS
- Start Redis
- Run database migrations
- Start the Django development server
- Start Celery worker and beat services

2. Create a superuser (if needed):
```bash
docker-compose exec web python manage.py createsuperuser
```

## Development Workflow

- The Django application code is mounted as a volume, so changes are reflected immediately
- Database and Redis data persist between container restarts
- Use `docker-compose down -v` to completely reset the containers and their volumes

## Troubleshooting

1. **Database Connection Issues**
   - Ensure the PostgreSQL container is running
   - Check environment variables in `.env` file
   - Verify network connectivity between containers
   - Check if PostGIS extension is properly initialized

2. **Redis Connection Issues**
   - Ensure Redis container is running
   - Check REDIS_URL environment variable
   - Verify Redis port is accessible

3. **Celery Issues**
   - Check Celery worker logs: `docker-compose logs celery_worker`
   - Check Celery beat logs: `docker-compose logs celery_beat`
   - Verify Redis connection is working
   - Ensure migrations are complete before Celery beat starts

4. **Django Application Issues**
   - Check Django logs: `docker-compose logs web`
   - Verify all required environment variables are set
   - Ensure migrations are up to date
