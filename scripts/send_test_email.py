from __future__ import annotations

import argparse
import smtplib
import sys
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings  # noqa: E402


def main() -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Send a test customer email to MailHog")
    parser.add_argument("--to", default=settings.mailhog_recipient)
    parser.add_argument("--subject", default="ArcVault dashboard unavailable")
    parser.add_argument(
        "--message",
        default="The dashboard stopped loading around 2pm EST. Multiple users affected.",
    )
    args = parser.parse_args()

    email = EmailMessage()
    email["From"] = "customer@example.com"
    email["To"] = args.to
    email["Subject"] = args.subject
    email["Date"] = format_datetime(datetime.now(UTC))
    email["Message-ID"] = make_msgid(domain="arcvault.local")
    email.set_content(args.message)
    with smtplib.SMTP(settings.mailhog_smtp_host, settings.mailhog_smtp_port, timeout=10) as smtp:
        smtp.send_message(email)
    print(f"Sent test email to {args.to} through MailHog SMTP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
