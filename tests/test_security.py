import jwt
import pytest

from app.security import (LoginRateLimiter, create_access_token, decode_access_token, hash_password, verify_password)
from app.tracking import generate_tracking_number, is_valid_tracking_number, normalise_tracking_number


def test_password_hash_roundtrip():
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass" and verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)
    assert hash_password("s3cret-pass") != h  # unique salt


def test_verify_password_tolerates_garbage():
    assert not verify_password("x", "not-a-hash")


def test_token_roundtrip_and_tamper():
    token = create_access_token(42)
    assert decode_access_token(token) == 42
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token[:-2] + "xx")


def test_rate_limiter_blocks_then_expires():
    now = [0.0]
    rl = LoginRateLimiter(max_failures=3, window_seconds=60, clock=lambda: now[0])
    for _ in range(3):
        assert rl.retry_after("k") == 0
        rl.record_failure("k")
    assert rl.retry_after("k") > 0
    now[0] = 61
    assert rl.retry_after("k") == 0


def test_tracking_numbers():
    n = generate_tracking_number()
    assert is_valid_tracking_number(n)
    assert normalise_tracking_number(f" {n[:3].lower()}-{n[3:]} ") == n
    assert not is_valid_tracking_number("ZNT00000000O")
