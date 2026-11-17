[Unit]
Description=Voracity2 Web UI (Flask)
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/voracity2
ExecStart=/opt/voracity2/.venv/bin/python src/voracity2/ui/app.py
Restart=always

[Install]
WantedBy=multi-user.target