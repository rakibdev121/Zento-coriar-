"""Tracking-number generation and normalisation."""
import re
import secrets

PREFIX = "ZNT"
# No 0/O/1/I/L to avoid look-alike characters when read out over the phone.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
BODY_LENGTH = 9
_PATTERN = re.compile(rf"^{PREFIX}[{ALPHABET}]{{{BODY_LENGTH}}}$")


def generate_tracking_number() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(BODY_LENGTH))


def normalise_tracking_number(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw or "").upper()


def is_valid_tracking_number(value: str) -> bool:
    return bool(_PATTERN.match(value))
