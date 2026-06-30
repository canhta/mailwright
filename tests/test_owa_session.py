import base64
import json

from mailwright.owa.session import OwaSession, jwt_exp


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")


def _make_jwt(exp: int) -> str:
    return f"Bearer {_b64({'alg': 'none'})}.{_b64({'exp': exp})}.sig"


class _Clock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class _Extractor:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.token


def test_jwt_exp_parses_and_tolerates_garbage():
    assert jwt_exp(_make_jwt(1000)) == 1000.0
    assert jwt_exp("garbage") is None
    assert jwt_exp("Bearer not.a.jwt") is None


def test_token_is_cached_until_near_expiry():
    clock = _Clock(0.0)
    ext = _Extractor(_make_jwt(1000))
    session = OwaSession(ext, clock=clock, skew_seconds=120)

    assert session.get_token() == ext.token
    assert ext.calls == 1

    clock.t = 500  # still well before exp(1000) - skew(120) = 880
    session.get_token()
    assert ext.calls == 1  # served from cache

    clock.t = 900  # past 880 -> must re-extract
    session.get_token()
    assert ext.calls == 2


def test_uses_fallback_ttl_when_token_has_no_exp():
    clock = _Clock(0.0)
    ext = _Extractor("Bearer opaque-no-jwt")
    session = OwaSession(ext, clock=clock, skew_seconds=120, fallback_ttl_seconds=1800)

    session.get_token()
    assert ext.calls == 1

    clock.t = 1000  # before 1800 - 120
    session.get_token()
    assert ext.calls == 1

    clock.t = 1700  # past 1680
    session.get_token()
    assert ext.calls == 2
