"""HTTP + optional TLS servers for the planted demo target."""

from __future__ import annotations

import ssl
import subprocess
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from src.opsec.demo_target.app import DemoHandler, TLS_SAN


def make_tls_pair(dest: Path, san: str = TLS_SAN) -> tuple[Path, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    cert = dest / "cert.pem"
    key = dest / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-days",
            "2",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=localhost",
            "-addext",
            f"subjectAltName=DNS:{san},DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def _bind(handler, host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd


def serve_in_thread(
    host: str = "127.0.0.1",
    http_port: int = 0,
    tls_port: int = 0,
    cert_dir: Path | None = None,
) -> dict:
    httpd = _bind(DemoHandler, host, http_port)
    tlsd = _bind(DemoHandler, host, tls_port)
    tmp = None
    if cert_dir is None:
        tmp = tempfile.TemporaryDirectory()
        cert_dir = Path(tmp.name)
    cert, key = make_tls_pair(cert_dir)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key))
    tlsd.socket = ctx.wrap_socket(tlsd.socket, server_side=True)
    threads = [
        threading.Thread(target=httpd.serve_forever, daemon=True),
        threading.Thread(target=tlsd.serve_forever, daemon=True),
    ]
    for t in threads:
        t.start()
    http_url = f"http://{host}:{httpd.server_address[1]}"
    tls_url = f"https://{host}:{tlsd.server_address[1]}"

    def stop() -> None:
        httpd.shutdown()
        tlsd.shutdown()
        httpd.server_close()
        tlsd.server_close()
        if tmp is not None:
            tmp.cleanup()

    return {"http": http_url, "https": tls_url, "stop": stop, "httpd": httpd, "tlsd": tlsd}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    p = argparse.ArgumentParser(description="SUTRANETRA localhost demo target")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--tls-port", type=int, default=8443)
    p.add_argument("--cert-dir", default="data/tor/certs")
    args = p.parse_args(argv)
    info = serve_in_thread(args.host, args.http_port, args.tls_port, Path(args.cert_dir))
    print("demo_target", info["http"], info["https"])
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        info["stop"]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
