from smarthealth.security import (
    LoginThrottle,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip_and_salting():
    h1, h2 = hash_password("s3cret", 1000), hash_password("s3cret", 1000)
    assert h1 != h2 and verify_password("s3cret", h1)
    assert not verify_password("wrong", h1)
    assert "s3cret" not in h1


def test_verify_rejects_malformed_hash():
    assert not verify_password("x", "garbage")
    assert not verify_password("x", "md5$1$00$00")


def test_token_roundtrip_expiry_and_tamper():
    tok = create_token({"uid": 1}, "k", 60, now=1000)
    assert decode_token(tok, "k", now=1010)["uid"] == 1
    assert decode_token(tok, "k", now=2000) is None          # expired
    assert decode_token(tok, "other", now=1010) is None      # wrong key
    payload, sig = tok.split(".")
    assert decode_token(f"{payload}x.{sig}", "k", now=1010) is None
    assert decode_token("not-a-token", "k") is None
    assert decode_token("", "k") is None


def test_throttle_blocks_then_recovers():
    th = LoginThrottle(max_failures=3, window=10)
    for i in range(3):
        assert not th.blocked("a", now=i)
        th.record_failure("a", now=i)
    assert th.blocked("a", now=3) and not th.blocked("b", now=3)
    assert not th.blocked("a", now=100)  # window elapsed
    th.record_failure("a", now=100)
    th.reset("a")
    assert not th.blocked("a", now=100)
