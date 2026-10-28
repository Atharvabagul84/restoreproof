"""Installed, versioned application assets; independent of current directory."""
from pathlib import Path

ASSETS = Path(__file__).with_name('assets')
