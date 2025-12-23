"""SSL certificate generation utilities for local HTTPS."""

import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_self_signed_cert(
    cert_path: Path,
    key_path: Path,
    hostnames: list[str] | None = None,
    days_valid: int = 365,
) -> tuple[Path, Path]:
    """Generate a self-signed certificate for local HTTPS.

    Args:
        cert_path: Path to write the certificate PEM file
        key_path: Path to write the private key PEM file
        hostnames: List of hostnames/IPs for the cert (default: localhost, 127.0.0.1)
        days_valid: How long the cert should be valid (default: 365 days)

    Returns:
        Tuple of (cert_path, key_path)
    """
    if hostnames is None:
        hostnames = ["localhost", "127.0.0.1"]

    # Generate private key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Build certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0]),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OBS Harness (Self-Signed)"),
    ])

    # Build Subject Alternative Names for all hostnames/IPs
    san_entries: list[x509.GeneralName] = []
    for hostname in hostnames:
        # Check if it's an IP address
        try:
            import ipaddress
            ip = ipaddress.ip_address(hostname)
            san_entries.append(x509.IPAddress(ip))
        except ValueError:
            # It's a hostname
            san_entries.append(x509.DNSName(hostname))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=days_valid))
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    # Write key file
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    # Write cert file
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return cert_path, key_path


def ensure_ssl_certs(
    cert_dir: Path,
    hostnames: list[str] | None = None,
    regenerate: bool = False,
) -> tuple[Path, Path]:
    """Ensure SSL certificates exist, generating if needed.

    Args:
        cert_dir: Directory to store certificates
        hostnames: List of hostnames/IPs for the cert
        regenerate: Force regeneration even if certs exist

    Returns:
        Tuple of (cert_path, key_path)
    """
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    if regenerate or not cert_path.exists() or not key_path.exists():
        return generate_self_signed_cert(cert_path, key_path, hostnames)

    return cert_path, key_path
