#!/usr/bin/env python3
"""Run the COMERCIAL-IA data pipeline end-to-end."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from commercial_ai.pipelines.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
