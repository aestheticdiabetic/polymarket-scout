"""
Rotates Polymarket L2 API credentials using py-clob-client.
Creates or derives a new API key from the wallet private key and writes to .env
"""
import os
import re
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv()

PRIVATE_KEY = os.environ["POLY_PRIVATE_KEY"]
OLD_API_KEY = os.environ.get("POLY_API_KEY", "")


def update_env(key: str, value: str, env_path: str = ".env"):
    with open(env_path, "r") as f:
        content = f.read()
    pattern = rf"^({re.escape(key)}=).*$"
    new_content = re.sub(pattern, rf"\g<1>{value}", content, flags=re.MULTILINE)
    if key not in new_content:
        new_content += f"\n{key}={value}"
    with open(env_path, "w") as f:
        f.write(new_content)


client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=POLYGON,
    key=PRIVATE_KEY,
)

print(f"Wallet address: {client.get_address()}")
print("Creating/deriving new API credentials...")

try:
    creds = client.create_or_derive_api_creds()
    print(f"  apiKey:     {creds.api_key}")
    print(f"  secret:     {creds.api_secret}")
    print(f"  passphrase: {creds.api_passphrase}")

    update_env("POLY_API_KEY", creds.api_key)
    update_env("POLY_API_SECRET", creds.api_secret)
    update_env("POLY_API_PASSPHRASE", creds.api_passphrase)
    print("\n.env updated successfully.")
except Exception as e:
    print(f"Failed: {e}")
