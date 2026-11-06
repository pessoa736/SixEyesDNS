import base64
import csv
import os
import random
import socket
import time
from pathlib import Path

import dns.exception
import dns.message
import dns.query


DNS_SERVER = os.getenv("DNS_SERVER", "dnsmasq")
DNS_PORT = int(os.getenv("DNS_PORT", "53"))
QUERY_COUNT = int(os.getenv("QUERY_COUNT", "30"))
QUERY_INTERVAL = float(os.getenv("QUERY_INTERVAL", "0.2"))
LABELS_PATH = Path(os.getenv("LABELS_PATH", "/data/query_labels.csv"))
RANDOM = random.Random(int(os.getenv("SEED", "42")))
ANOMALY_RATE = float(os.getenv("ANOMALY_RATE", "0.5"))
NORMAL_SERVICES = ("www", "api", "mail", "cdn", "status", "auth", "metrics")
NORMAL_REGIONS = ("us-east", "us-west", "eu-west", "sa-east", "ap-south")
NORMAL_VERSIONS = ("v1", "v2", "v3")
FICTIONAL_NAMES = (
	("luma", "ferraz"),
	("nilo", "ventura"),
	("cora", "valen"),
	("tavi", "moura"),
	("mila", "soren"),
	("zeca", "dourado"),
)
def random_bytes(size: int = 18) -> bytes:
	return bytes(RANDOM.randrange(256) for _ in range(size))


def normal_domain(index: int) -> str:
	service = NORMAL_SERVICES[index % len(NORMAL_SERVICES)]
	region = NORMAL_REGIONS[index % len(NORMAL_REGIONS)]
	version = NORMAL_VERSIONS[index % len(NORMAL_VERSIONS)]
	first_name, last_name = FICTIONAL_NAMES[index % len(FICTIONAL_NAMES)]
	pattern = index % 9

	if pattern == 0:
		return f"{service}.normal.test"
	if pattern == 1:
		return f"{service}.{region}.normal.test"
	if pattern == 2:
		return f"{version}.{service}.normal.test"
	if pattern == 3:
		return f"{service}-{index % 12}.{region}.normal.test"
	if pattern == 4:
		return f"node-{index % 20}.{service}.normal.test"
	if pattern == 5:
		return f"telemetry.{region}.{service}.normal.test"
	if pattern == 6:
		return f"{first_name}.{last_name}.normal.test"
	if pattern == 7:
		return f"{first_name}-{index % 8}.{service}.normal.test"
	return f"{first_name}.{region}.{service}.normal.test"


def anomalous_domain(index: int) -> tuple[str, str]:
	payload = random_bytes(8 + (index % 5) * 4)
	family = ("base32", "hex", "base64")[index % 3]

	if family == "base32":
		encoded = base64.b32encode(payload).decode("ascii").rstrip("=").lower()
	elif family == "hex":
		encoded = payload.hex()
	else:
		encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

	return f"{encoded}.tunnel.test", family


def send_query(domain: str) -> None:
	request = dns.message.make_query(domain, "A")
	server_address = socket.gethostbyname(DNS_SERVER)
	response = dns.query.udp(request, server_address, port=DNS_PORT, timeout=3)
	response.rcode()


def main() -> None:
	LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)

	with LABELS_PATH.open("w", newline="") as labels_file:
		writer = csv.writer(labels_file)
		writer.writerow(("query", "family", "label", "seed"))

		for index in range(QUERY_COUNT):
			if RANDOM.random() >= ANOMALY_RATE:
				domain = normal_domain(index)
				family = "normal"
				label = "normal"
			else:
				domain, family = anomalous_domain(index)
				label = "suspeita"

			try:
				send_query(domain)
				print(f"consulta={domain} familia={family} rotulo={label}", flush=True)
			except dns.exception.DNSException as error:
				print(f"falha={domain} erro={error}", flush=True)
				continue

			writer.writerow(
				(
					domain,
					family,
					label,
					os.getenv("SEED", "42"),
				)
			)
			labels_file.flush()
			time.sleep(QUERY_INTERVAL)


if __name__ == "__main__":
	main()
