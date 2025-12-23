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
        default=8080,
        help="Port to bind to (default: 8080)",
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
    parser.add_argument(
        "--https",
        action="store_true",
        help="Enable HTTPS with auto-generated self-signed certificate",
    )
    parser.add_argument(
        "--ssl-cert",
        type=Path,
        default=None,
        help="Path to SSL certificate file (use with --ssl-key)",
    )
    parser.add_argument(
        "--ssl-key",
        type=Path,
        default=None,
        help="Path to SSL private key file (use with --ssl-cert)",
    )

    args = parser.parse_args()

    # Import here to avoid slow startup for --help
    import uvicorn

    # Handle SSL configuration
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None

    if args.ssl_cert and args.ssl_key:
        # Use provided certificates
        ssl_certfile = str(args.ssl_cert)
        ssl_keyfile = str(args.ssl_key)
    elif args.https:
        # Auto-generate self-signed certificates
        from .ssl_utils import ensure_ssl_certs

        cert_dir = Path.cwd() / ".ssl"
        hostnames = ["localhost", "127.0.0.1"]

        # Add the bind host if it's not already included
        if args.host not in ("0.0.0.0", "127.0.0.1", "localhost"):
            hostnames.append(args.host)

        # If binding to 0.0.0.0, try to get local IP
        if args.host == "0.0.0.0":
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                if local_ip not in hostnames:
                    hostnames.append(local_ip)
            except Exception:
                pass

        cert_path, key_path = ensure_ssl_certs(cert_dir, hostnames)
        ssl_certfile = str(cert_path)
        ssl_keyfile = str(key_path)

        print(f"\n  SSL certificates generated in {cert_dir}/")
        print(f"  Hostnames: {', '.join(hostnames)}")

    protocol = "https" if ssl_certfile else "http"

    print(f"\n  OBS Audio Harness")
    print(f"  ─────────────────")
    print(f"  Dashboard:    {protocol}://{args.host}:{args.port}/")
    print(f"  Browser URL:  {protocol}://{args.host}:{args.port}/channel/{{name}}")
    print(f"  Editor:       {protocol}://{args.host}:{args.port}/editor")
    print(f"  API Docs:     {protocol}://{args.host}:{args.port}/docs")
    if ssl_certfile:
        print(f"\n  Note: Browser will show security warning for self-signed cert.")
        print(f"        Click 'Advanced' -> 'Proceed' to continue.")
    print()

    if args.reload:
        # Use import string for reload support
        uvicorn.run(
            "obs_harness.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
    else:
        from .app import create_app
        app = create_app(db_url=args.db, static_dir=args.static_dir)
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )


if __name__ == "__main__":
    main()
