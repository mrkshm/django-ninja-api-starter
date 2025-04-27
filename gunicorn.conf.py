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