"""
scripts/cleanup_orphaned_files.py

Lists stored files that no database row references any more, and deletes
them with --apply. Dry-run by default. See modules/files/cleanup.py for
exactly what counts as an orphan (never anything newer than --grace-hours).

Run:
    cd backend && .venv\\Scripts\\python -m scripts.cleanup_orphaned_files              # report only
    cd backend && .venv\\Scripts\\python -m scripts.cleanup_orphaned_files --apply      # delete
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402,F401
from config.database import SessionLocal  # noqa: E402
from core.object_storage import get_object_storage  # noqa: E402
from modules.files.cleanup import delete_orphans, find_orphans  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Find / delete orphaned stored files.")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default: report only)")
    parser.add_argument("--grace-hours", type=float, default=24, help="Ignore files newer than this (default 24)")
    args = parser.parse_args()

    storage = get_object_storage()
    db = SessionLocal()
    try:
        orphans = find_orphans(db, storage, args.grace_hours)
    finally:
        db.close()
    total = sum(len(v) for v in orphans.values())
    for bucket, keys in orphans.items():
        print(f"{bucket}: {len(keys)} orphaned file(s)")
        for key in keys[:50]:
            print(f"  {key}")
    if args.apply and total:
        print(f"Deleted {delete_orphans(storage, orphans)} file(s).")
    elif total:
        print("Dry run — re-run with --apply to delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
