from __future__ import annotations

import re

# docker compose logs: "insurgency-sandstorm  | actual line"
_COMPOSE_PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\s+\|\s+")


def normalize_line(line: str) -> str:
    line = line.replace("\r", "").rstrip("\n")
    match = _COMPOSE_PREFIX.match(line)
    if match:
        line = line[match.end():]
    return line
