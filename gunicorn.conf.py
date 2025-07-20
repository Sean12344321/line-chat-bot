# gunicorn.conf.py
# Store this file in: /home/ec2-user/line-chat-bot/gunicorn.conf.py

import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = 1  # IMPORTANT: Keep at 1 for APScheduler to avoid duplicate jobs
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
#accesslog = "/home/ec2-user/line-chat-bot/logs/gunicorn_access.log"
#errorlog = "/home/ec2-user/line-chat-bot/logs/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'line_chat_bot'

# Server mechanics
daemon = False  # Set to True if you want it to run as daemon
pidfile = "/tmp/gunicorn_line_chat_bot.pid"
user = "ec2-user"
group = "ec2-user"
tmp_upload_dir = None

# SSL (uncomment if you need HTTPS)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

def when_ready(server):
    server.log.info("Server is ready. Spawning workers")
