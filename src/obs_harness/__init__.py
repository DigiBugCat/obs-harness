"""OBS Audio Harness - Push audio and animated text to OBS via browser sources."""

__version__ = "0.2.0"

from .app import ConnectionManager, OBSHarness, create_app

__all__ = ["create_app", "OBSHarness", "ConnectionManager"]
