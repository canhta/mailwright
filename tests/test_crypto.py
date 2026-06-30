from mailwright.crypto import decrypt, encrypt, generate_key


def test_encrypt_decrypt_roundtrip():
    key = generate_key()
    token = encrypt(b"secret-bytes", key)
    assert token != b"secret-bytes"
    assert decrypt(token, key) == b"secret-bytes"
