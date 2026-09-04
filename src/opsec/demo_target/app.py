"""Localhost demo hidden-service backend (SPEC.md §12.1). Not a third-party HS."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

CLEARNET_DOMAIN = "erowid.org"
CLEARNET_IMG = "https://www.erowid.org/favicon.ico"
CLEARNET_CSS = "https://www.erowid.org/general/include/css.css"
GIT_REMOTE = "https://github.com/Venkat-Kolasani/SUTRANETRA.git"
SERVER_AT_HOST = "demo-host.sutranetra.invalid"
ENV_BODY = "DB_HOST=db.erowid.org\nAPP_DEBUG=1\n"
DEFAULT_PAGE = "Welcome to nginx!\n"
TLS_SAN = "erowid.org"

HOME_HTML = f"""<!doctype html>
<html><head>
<title>SUTRANETRA demo vendor stall</title>
<link rel="stylesheet" href="{CLEARNET_CSS}">
<link rel="icon" href="{CLEARNET_IMG}">
</head><body>
<h1>demo stall (localhost only)</h1>
<img src="{CLEARNET_IMG}" alt="leak">
<p>planted clearnet resource — headline leak into CT pivot</p>
</body></html>
"""

GIT_CONFIG = f"""[core]
	repositoryformatversion = 0
[remote "origin"]
	url = {GIT_REMOTE}
	fetch = +refs/heads/*:refs/remotes/origin/*
"""

SERVER_STATUS = f"""Apache Server Status for {SERVER_AT_HOST}

Server at {SERVER_AT_HOST} Port 80
"""

DIR_LISTING = """<!doctype html>
<html><head><title>Index of /files/</title></head>
<body><h1>Index of /files/</h1>
<ul><li><a href="/files/notes.txt">notes.txt</a></li></ul>
</body></html>
"""

BACKUP_ZIP = b"PK\x03\x04demo-backup"


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def _send(self, code: int, body: bytes, content_type: str = "text/html") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Server", "Apache/2.4.41 (Ubuntu)")
        self.send_header("X-Powered-By", "PHP/7.4.3")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, HOME_HTML.encode())
        elif path == "/server-status":
            self._send(200, SERVER_STATUS.encode(), "text/plain")
        elif path == "/.git/config":
            self._send(200, GIT_CONFIG.encode(), "text/plain")
        elif path == "/.env":
            self._send(200, ENV_BODY.encode(), "text/plain")
        elif path == "/backup.zip":
            self._send(200, BACKUP_ZIP, "application/zip")
        elif path == "/config.php.bak":
            self._send(200, b"<?php $db='db.erowid.org';\n", "text/plain")
        elif path in ("/files", "/files/"):
            self._send(200, DIR_LISTING.encode())
        elif path == "/it-works":
            self._send(200, DEFAULT_PAGE.encode(), "text/plain")
        else:
            self._send(404, b"not found", "text/plain")
