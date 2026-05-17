"""Thin wrapper for interactive agentic play.

Full implementation lives in metarpg.agentic.play_cli.
"""
from __future__ import annotations

import sys

sys.path.insert(0, r"E:\GameDesign\MetaRPG_Dev")

from metarpg.agentic.play_cli import main

if __name__ == "__main__":
    sys.exit(main())
