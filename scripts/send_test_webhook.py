from __future__ import annotations

import argparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one ArcVault test webhook")
    parser.add_argument("--url", default="http://localhost:8000/webhooks/intake")
    parser.add_argument("--secret", default="change-me")
    args = parser.parse_args()
    payload = {
        "event_id": "demo-001",
        "source": "Email",
        "message": "Several users cannot load the dashboard.",
    }
    response = httpx.post(
        args.url,
        headers={"X-Webhook-Secret": args.secret},
        json=payload,
        timeout=10,
    )
    print(response.status_code, response.text)
    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
