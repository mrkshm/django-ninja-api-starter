# Gunicorn Setup Guide

This document explains how to switch between development and production modes in the Django application.

## Current Setup

The project supports two modes of operation:
- Development: Uses Django's development server
- Production: Uses Gunicorn with optimized settings

## Switching to Production Mode

To switch to production mode with Gunicorn:

1. Set the environment variable:
```bash
DJANGO_ENV=production docker-compose up
```

Or add to your `.env` file for persistence:
```bash
DJANGO_ENV=production
```

2. Rebuild and start containers:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up
```

## Current Configuration

The Gunicorn configuration (`gunicorn.conf.py`) includes:

```python
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Timeouts
timeout = 120
keepalive = 5

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
```

## Monitoring

Gunicorn provides access and error logs in the container output. In production, you might want to:
1. Configure log rotation
2. Set up log aggregation
3. Monitor worker health

## Troubleshooting

1. **Worker Timeouts**
   - Increase `timeout` value in `gunicorn.conf.py`
   - Check for long-running tasks
   - Consider moving heavy tasks to Celery

2. **Memory Issues**
   - Reduce number of workers
   - Monitor worker memory usage
   - Consider using `--preload` for memory sharing

3. **Performance Issues**
   - Adjust worker class based on workload
   - Tune number of workers and threads
   - Consider using a reverse proxy (Nginx)

## Best Practices

1. **Security**
   - Run as non-root user (already configured)
   - Set appropriate file permissions (already configured)
   - Use HTTPS in production
   - Configure proper timeouts (already configured)

2. **Performance**
   - Use appropriate worker class (gthread configured)
   - Monitor and adjust worker count
   - Enable keep-alive connections
   - Use a reverse proxy for static files

3. **Reliability**
   - Implement proper logging (configured)
   - Set up monitoring
   - Configure automatic restarts
   - Use process management (e.g., systemd)
