"""Verify public IPv4 TLS with the operating system trust store; no bypass."""
import json
from pathlib import Path
import socket
import ssl
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud_config import load_private
host = load_private()[0].get('public_host', '')
if not host:
    raise SystemExit('Set public_host in private settings before checking your server.')
with socket.create_connection((host, 443), timeout=15) as sock:
    with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as tls:
        cert = tls.getpeercert()
        result = {'verified': True, 'tls': tls.version(), 'issuer': cert['issuer'],
                  'san': cert['subjectAltName'], 'not_before': cert['notBefore'],
                  'not_after': cert['notAfter']}
        tls.sendall(f'GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'.encode())
        result['http_status'] = tls.recv(256).split(b'\r\n')[0].decode()
(ROOT / 'evidence').mkdir(exist_ok=True)
(ROOT / 'evidence/public-ip-tls.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
