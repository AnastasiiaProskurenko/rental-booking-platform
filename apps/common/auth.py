

def is_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True

    fn = getattr(user, "is_admin", None)
    if callable(fn):
        try:
            return bool(fn())
        except TypeError:
            return bool(fn)

    return False


def is_owner(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False

    fn = getattr(user, "is_owner", None)
    if callable(fn):
        try:
            return bool(fn())
        except TypeError:
            return bool(fn)

    return False
