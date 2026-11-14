"""Tests each regional pooler by TCP connect + Supabase handshake to find the project region."""

import socket
import struct
import sys

REF = "izxneacavxfcjklnsftd"

REGIONS = [
    "us-east-1", "ap-south-1", "ap-southeast-1", "ap-southeast-2",
    "ap-northeast-1", "us-west-1", "us-east-2", "us-west-2",
    "sa-east-1", "eu-north-1", "eu-west-3", "eu-central-2",
    "ap-east-1", "ca-central-1", "ap-southeast-3", "ap-northeast-2",
    "eu-central-1", "eu-west-1", "eu-west-2",
]
PREFIXES = ["aws-0", "aws-1"]


def tcp_probe(ip: str, port: int, timeout: float = 4.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            # PostgreSQL SSLRequest: length 8, code 80877103
            sock.sendall(struct.pack("!ii", 8, 80877103))
            response = sock.recv(1)
            return response == b"S" or response == b"N"
    except OSError:
        return False


results: list[tuple[str, str, str]] = []
for region in REGIONS:
    for prefix in PREFIXES:
        host = f"{prefix}-{region}.pooler.supabase.com"
        try:
            ip = socket.gethostbyname(host)
        except OSError:
            continue
        reachable = tcp_probe(ip, 5432)
        reachable6543 = tcp_probe(ip, 6543)
        if reachable or reachable6543:
            results.append((region, host, "5432" if reachable else ("6543" if reachable6543 else "-")))
            print(f"REACHABLE: {host} ({ip}) ports 5432={reachable} 6543={reachable6543}")
        else:
            print(f"unreachable: {host}")

if not results:
    print("NO REACHABLE POOLER — network-level block suspected")
    sys.exit(1)
print(f"\nreachable regions: {[r[0] for r in results]}")
