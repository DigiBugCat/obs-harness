"""CLI entry point for OBS Audio Harness."""

import argparse
import asyncio
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
        "--https-port",
        type=int,
        default=None,
        help="HTTPS port when using --https (default: port + 363, e.g., 8080 -> 8443)",
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
        help="Enable HTTPS with auto-generated self-signed certificate (runs both HTTP and HTTPS)",
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
    https_port = args.https_port or (args.port + 363)  # 8080 -> 8443

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

    print(f"\n  OBS Audio Harness")
    print(f"  ─────────────────")
    print(f"  Dashboard:    http://{args.host}:{args.port}/")
    if ssl_certfile:
        print(f"  Dashboard:    https://{args.host}:{https_port}/")
    print(f"  Browser URL:  http://{args.host}:{args.port}/channel/{{name}}")
    if ssl_certfile:
        print(f"  Browser URL:  https://{args.host}:{https_port}/channel/{{name}}")
    print(f"  Editor:       http://{args.host}:{args.port}/editor")
    print(f"  API Docs:     http://{args.host}:{args.port}/docs")
    if ssl_certfile:
        print(f"\n  Note: Browser will show security warning for self-signed cert.")
        print(f"        Click 'Advanced' -> 'Proceed' to continue.")
    print()

    if args.reload:
        if ssl_certfile:
            print("  Warning: --reload with --https only runs HTTPS server.")
            print("           Run without --reload for both HTTP and HTTPS.\n")
        # Use import string for reload support (single server only)
        uvicorn.run(
            "obs_harness.app:create_app",
            factory=True,
            host=args.host,
            port=https_port if ssl_certfile else args.port,
            reload=True,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
    elif ssl_certfile:
        # Run both HTTP and HTTPS servers
        asyncio.run(_run_dual_servers(args, ssl_certfile, ssl_keyfile, https_port))
    else:
        # HTTP only
        from .app import create_app
        app = create_app(db_url=args.db, static_dir=args.static_dir)
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
        )


async def _run_dual_servers(args, ssl_certfile: str, ssl_keyfile: str, https_port: int) -> None:
    """Run both HTTP and HTTPS servers concurrently."""
    import uvicorn
    from .app import create_app

    # Create a single app instance shared by both servers
    app = create_app(db_url=args.db, static_dir=args.static_dir)

    # Configure HTTP server
    http_config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    http_server = uvicorn.Server(http_config)

    # Configure HTTPS server
    https_config = uvicorn.Config(
        app,
        host=args.host,
        port=https_port,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        log_level="info",
    )
    https_server = uvicorn.Server(https_config)

    # Run both servers concurrently
    await asyncio.gather(
        http_server.serve(),
        https_server.serve(),
    )


if __name__ == "__main__":
    main()
