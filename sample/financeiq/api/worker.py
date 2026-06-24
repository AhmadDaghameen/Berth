"""FinanceIQ worker — demo background processor."""
import time, os

if __name__ == "__main__":
    print(f"[worker] Starting (version={os.environ.get('APP_VERSION', 'dev')})")
    while True:
        print("[worker] Processing market data tick …")
        time.sleep(10)
