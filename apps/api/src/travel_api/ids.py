from ulid import ULID


def new_id(prefix: str) -> str:
    """A prefixed ULID such as ``trip_01J9...``."""
    return f"{prefix}_{ULID()}"
