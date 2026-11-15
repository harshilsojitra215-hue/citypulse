"""Privacy check on app/data/engine.js: no author fields, e-mails or @handles may reach the website."""
import json
import re
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[2] / "app" / "data" / "engine.js"


def main():
    s = P.read_text(encoding="utf-8")
    d = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";"))
    print({k: len(json.dumps(v)) // 1024 for k, v in d.items()}, "KB per block")
    authors = re.findall(r'"author[a-z_]*"\s*:\s*"[^"]+', s)
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", s)
    handles = [h for h in re.findall(r"(?<![\w/.])@[A-Za-z0-9_]{3,}", s)]
    sys.path.insert(0, str(Path(__file__).resolve().parent))   # python -I does not add the script folder
    import snapshot
    accounts = [u for u in re.findall(r'https?://[^"\s]+', s) if snapshot.ACCOUNT_URL.search(u)]
    print(f"author fields with a value: {len(authors)}, e-mails: {len(emails)}, @handles: {len(handles)}, "
          f"account-naming links: {len(accounts)}")
    return 1 if (authors or emails or handles or accounts) else 0


if __name__ == "__main__":
    sys.exit(main())
