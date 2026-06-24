"""Stub migration runner (stands in for alembic in the demo)."""
import sys

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "upgrade":
        print("[migrations] Running database migrations … done.")
    else:
        print(f"[migrations] Unknown command: {cmd}")
        sys.exit(1)
