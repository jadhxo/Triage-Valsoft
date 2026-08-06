from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings  # noqa: E402
from app.integrations.mailhog import MailHogWatcher  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward MailHog email into ArcVault intake")
    parser.add_argument("--once", action="store_true", help="Poll once, report counts, and exit")
    args = parser.parse_args()
    settings = Settings()
    if settings.mail_trigger != "mailhog":
        print("Set MAIL_TRIGGER=mailhog in .env before starting the watcher.", file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    watcher = MailHogWatcher(settings)
    if args.once:
        try:
            result = watcher.poll_once()
        except (httpx.HTTPError, ValueError) as exc:
            print(f"MailHog poll failed: {exc}", file=sys.stderr)
            return 1
        print(
            f"fetched={result.fetched} forwarded={result.forwarded} "
            f"skipped={result.skipped} failed={result.failed}"
        )
        return 1 if result.failed else 0

    print(
        f"Watching {settings.mailhog_recipient} at {settings.mailhog_api_url}; "
        "press Ctrl+C to stop."
    )
    try:
        watcher.run_forever()
    except KeyboardInterrupt:
        print("MailHog watcher stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
