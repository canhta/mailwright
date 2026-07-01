import pytest

from mailwright.crypto import generate_key
from mailwright.owa.session import OwaLoginRequired
from mailwright.owa.state_store import (
    deserialize_state,
    read_state_file,
    serialize_state,
    write_state_file,
)


def test_serialize_deserialize_roundtrip():
    key = generate_key()
    state = {"cookies": [{"name": "ESTSAUTH", "value": "x"}], "origins": []}

    blob = serialize_state(state, key)

    assert blob != str(state).encode()
    assert deserialize_state(blob, key) == state


def test_write_then_read_file_roundtrip(tmp_path):
    key = generate_key()
    state = {"cookies": [], "origins": [{"origin": "https://outlook.cloud.microsoft"}]}
    path = tmp_path / "nested" / "owa_state.enc"

    write_state_file(str(path), state, key)

    assert path.exists()
    assert read_state_file(str(path), key) == state


def test_read_missing_file_raises_owa_login_required(tmp_path):
    key = generate_key()
    missing = tmp_path / "missing.enc"

    with pytest.raises(OwaLoginRequired):
        read_state_file(str(missing), key)
