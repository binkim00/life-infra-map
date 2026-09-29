"""Interactive server-only entry of OAuth credentials without shell history or log output."""

import getpass
import os
from pathlib import Path


ENV_PATH = Path(__file__).with_name(".env")
PUBLIC_BASE_URL = "https://life-infra-map-db.taile29cc8.ts.net"
PROVIDERS = ("GOOGLE", "NAVER", "KAKAO")


def safe_value(value):
    if any(character in value for character in "\r\n#"):
        raise ValueError("Credential contains unsupported characters")
    return value


def main():
    existing = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                existing[key] = value
    print("OAuth client ID and secret values are entered here, never in chat or shell history.")
    updates = {}
    for provider in PROVIDERS:
        client_id = safe_value(input(f"{provider} client ID (Enter to keep current): ").strip())
        if not client_id:
            continue
        secret = safe_value(getpass.getpass(f"{provider} client secret: ").strip())
        if not secret:
            raise ValueError(f"{provider} secret is required when its client ID is supplied")
        updates[f"SOCIAL_{provider}_CLIENT_ID"] = client_id
        updates[f"SOCIAL_{provider}_CLIENT_SECRET"] = secret
    merged = {**existing, **updates}
    enabled = any(merged.get(f"SOCIAL_{provider}_CLIENT_ID") and
                  merged.get(f"SOCIAL_{provider}_CLIENT_SECRET") for provider in PROVIDERS)
    if not enabled:
        print("No provider is configured. No file changed.")
        return
    merged["SOCIAL_LOGIN_ENABLED"] = "true"
    merged["SOCIAL_PUBLIC_BASE_URL"] = PUBLIC_BASE_URL
    preserved = [line for line in ENV_PATH.read_text(encoding="utf-8").splitlines()
                 if "=" not in line or line.split("=", 1)[0] not in merged] if ENV_PATH.exists() else []
    os.umask(0o077)
    temporary = ENV_PATH.with_suffix(".env.tmp")
    try:
        temporary.write_text("\n".join([*preserved, *(f"{key}={value}" for key, value in merged.items())]) + "\n",
                             encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, ENV_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    print("Social login settings saved with owner-only permissions. Values were not printed.")


if __name__ == "__main__":
    main()
