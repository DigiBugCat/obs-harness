"""CLI entry point for OBS Audio Harness."""

import argparse
from pathlib import Path


def main() -> None:
    """Run the OBS Harness server."""
    parser = argparse.ArgumentParser(
        description="OBS Audio Harness - Push audio and text to OBS browser sources"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--db",
        default="sqlite+aiosqlite:///obs_harness.db",
        help="Database URL (default: sqlite+aiosqlite:///obs_harness.db)",
    )
    parser.add_argument(
        "--static-dir",
        type=Path,
        default=None,
        help="Path to static files directory",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    args = parser.parse_args()

    # Import here to avoid slow startup for --help
    import uvicorn

    from .app import create_app

    app = create_app(db_url=args.db, static_dir=args.static_dir)

    print(f"\n  OBS Audio Harness")
    print(f"  ─────────────────")
    print(f"  Dashboard:    http://{args.host}:{args.port}/")
    print(f"  Browser URL:  http://{args.host}:{args.port}/channel/{{name}}")
    print(f"  Editor:       http://{args.host}:{args.port}/editor")
    print(f"  API Docs:     http://{args.host}:{args.port}/docs")
    print()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
