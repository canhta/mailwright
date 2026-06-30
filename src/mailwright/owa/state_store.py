import json
from pathlib import Path

from mailwright.crypto import decrypt, encrypt
from mailwright.owa.session import OwaLoginRequired


def serialize_state(state: dict, key: str) -> bytes:
    return encrypt(json.dumps(state).encode("utf-8"), key)


def deserialize_state(blob: bytes, key: str) -> dict:
    return json.loads(decrypt(blob, key).decode("utf-8"))  # type: ignore[no-any-return]


def write_state_file(path: str, state: dict, key: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(serialize_state(state, key))


def read_state_file(path: str, key: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise OwaLoginRequired(f"No OWA session found at {path}; run `login`.")
    return deserialize_state(p.read_bytes(), key)
