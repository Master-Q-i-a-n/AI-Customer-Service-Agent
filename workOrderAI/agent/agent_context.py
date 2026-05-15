from contextvars import ContextVar


_current_username = ContextVar("current_username", default="")


def set_current_username(username: str | None):
    return _current_username.set(str(username or "").strip())


def reset_current_username(token) -> None:
    _current_username.reset(token)


def get_current_username_value() -> str:
    return _current_username.get() or ""
