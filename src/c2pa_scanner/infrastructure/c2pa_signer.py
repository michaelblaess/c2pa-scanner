"""C2PA-Signierer: erzeugt ein Testbild mit eingebettetem C2PA-Manifest.

Dient als Positiv-Testfall und als 'Testbild erstellen'-Feature. Das verwendete
Zertifikat ist eine frisch erzeugte Wegwerf-Kette (Test-Root + Leaf) - NICHT
vertrauenswuerdig und ausdruecklich nur fuer Testzwecke.
"""

from __future__ import annotations

import datetime
import io
import json
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from PIL import Image, ImageDraw

DIGITAL_SOURCE_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
TRAINED_ALGORITHMIC_MEDIA = DIGITAL_SOURCE_BASE + "trainedAlgorithmicMedia"
COMPOSITE_WITH_TRAINED = DIGITAL_SOURCE_BASE + "compositeWithTrainedAlgorithmicMedia"


def _make_test_chain() -> tuple[bytes, ec.EllipticCurvePrivateKey]:
    """Erzeugt eine C2PA-profilkonforme Wegwerf-Zertifikatskette (Root-CA + Leaf).

    Die Chain-Verlinkung ueber Subject/Authority Key Identifier ist noetig, sonst
    lehnt c2pa den Signaturzertifikat als 'certificate is invalid' ab.
    """
    not_before = datetime.datetime(2026, 1, 1)
    not_after = datetime.datetime(2035, 1, 1)

    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "c2pa-scanner test root")])
    root_ski = x509.SubjectKeyIdentifier.from_public_key(root_key.public_key())
    root_cert = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(root_ski, critical=False)
        .sign(root_key, hashes.SHA256())
    )

    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "c2pa-scanner test signer")])
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(root_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )

    chain = (
        leaf_cert.public_bytes(serialization.Encoding.PEM)
        + root_cert.public_bytes(serialization.Encoding.PEM)
    )
    return chain, leaf_key


def _make_placeholder_image(label_text: str) -> bytes:
    """Erzeugt ein einfaches JPEG mit sichtbarem Hinweistext."""
    img = Image.new("RGB", (640, 400), (24, 96, 168))
    draw = ImageDraw.Draw(img)
    draw.rectangle((16, 16, 623, 383), outline=(255, 255, 255), width=2)
    draw.text((32, 40), "c2pa-scanner", fill=(255, 255, 255))
    draw.text((32, 70), f"Testbild - {label_text}", fill=(226, 226, 226))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def create_test_image(
    dest: Path,
    *,
    source_type: str = TRAINED_ALGORITHMIC_MEDIA,
    source_image: bytes | None = None,
    label_text: str = "KI-generiert",
) -> Path:
    """Schreibt ein C2PA-signiertes JPEG mit dem angegebenen digitalSourceType.

    Ohne source_image wird ein Platzhalterbild erzeugt. Rueckgabe ist der Zielpfad.
    """
    from c2pa import Builder, C2paSigningAlg, ContextBuilder, Settings, Signer

    chain, leaf_key = _make_test_chain()

    def sign_cb(data: bytes) -> bytes:
        # COSE ES256 erwartet rohe r||s-Signatur (je 32 Byte), nicht DER.
        der = leaf_key.sign(data, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    source = source_image if source_image is not None else _make_placeholder_image(label_text)
    manifest = {
        "claim_generator_info": [{"name": "c2pa-scanner", "version": "0.1.0"}],
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {"actions": [{"action": "c2pa.created", "digitalSourceType": source_type}]},
            }
        ],
    }

    signer = Signer.from_callback(sign_cb, C2paSigningAlg.ES256, chain.decode("ascii"), None)
    settings = Settings.from_dict({"verify": {"verify_after_sign": False, "verify_trust": False}})
    context = ContextBuilder().with_settings(settings).build()

    dest.parent.mkdir(parents=True, exist_ok=True)
    with (
        Builder.from_json(json.dumps(manifest), context=context) as builder,
        io.BytesIO(source) as src,
        dest.open("wb") as out,
    ):
        builder.sign(signer, "image/jpeg", src, out)
    return dest
