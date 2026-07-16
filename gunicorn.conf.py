import os

# Server socket
bind = "0.0.0.0:8000"

# Worker processes
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "2"))

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Timeouts
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
