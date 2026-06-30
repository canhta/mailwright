from cryptography.fernet import Fernet


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


def encrypt(data: bytes, key: str) -> bytes:
    return Fernet(key.encode("ascii")).encrypt(data)


def decrypt(token: bytes, key: str) -> bytes:
    return Fernet(key.encode("ascii")).decrypt(token)
