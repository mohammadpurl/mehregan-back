"""
Print bcrypt hash for use in SQL INSERT into users.hashed_password.

  python scripts/hash_password.py "MyStrongPass"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import get_password_hash


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate bcrypt password hash")
    parser.add_argument("password", help="Plain password to hash")
    args = parser.parse_args()
    hashed = get_password_hash(args.password)
    print(hashed)
    print()
    print("-- paste into SQL, e.g.:")
    print(f"-- hashed_password := '{hashed}'")


if __name__ == "__main__":
    main()
