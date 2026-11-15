"""Load live/.env into os.environ without printing anything. Used by the engine bridge and the launcher."""
import os
import re
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"


def load(keys=None) -> list:
    """Set the variables from live/.env that are not already set. Returns the names that were set (never values)."""
    done = []
    if not ENV.exists():
        return done
    for line in ENV.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*(\S+)\s*$", line)
        if not m or (keys and m.group(1) not in keys):
            continue
        if not os.environ.get(m.group(1)):
            os.environ[m.group(1)] = m.group(2)
            done.append(m.group(1))
    return done
