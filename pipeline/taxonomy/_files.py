"""Reads the YAML files that live next to the taxonomy modules."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

TAXONOMY_DIR = Path(__file__).resolve().parent


@cache
def read_yaml(filename: str) -> dict[str, Any]:
    """Parsed contents of a taxonomy file. Cached: callers must not mutate the result."""
    return yaml.safe_load((TAXONOMY_DIR / filename).read_text(encoding="utf-8"))
