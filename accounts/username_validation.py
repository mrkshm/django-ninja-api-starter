import string


USERNAME_MAX_LENGTH = 50
USERNAME_ALLOWED_CHARS = set(string.ascii_letters + string.digits + "._")
USERNAME_ALLOWED_DESCRIPTION = "letters, numbers, dots, and underscores"


def validate_username_value(username: str) -> tuple[bool, str | None]:
    if not username or len(username) > USERNAME_MAX_LENGTH:
        return False, "Username must be 1-50 characters."
    if any(char not in USERNAME_ALLOWED_CHARS for char in username):
        return False, f"Username may only contain {USERNAME_ALLOWED_DESCRIPTION}."
    return True, None
