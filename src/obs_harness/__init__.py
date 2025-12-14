"""OBS Audio Harness - Push audio and animated text to OBS via browser sources."""

from .app import ConnectionManager, OBSHarness, create_app

__version__ = "0.1.0"
__all__ = ["create_app", "OBSHarness", "ConnectionManager"]
