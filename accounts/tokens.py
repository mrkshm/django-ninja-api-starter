import hashlib
import secrets
import string


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_token_hash(token: str) -> bool:
    return len(token) == 64 and all(char in string.hexdigits for char in token)


def generate_hashed_token() -> str:
    return hash_token(generate_raw_token())
