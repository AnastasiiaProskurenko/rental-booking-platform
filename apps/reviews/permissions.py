from rest_framework import permissions


class IsCustomerOrReadOnly(permissions.BasePermission):
    """
    Дозволяє читання всім, редагування тільки автору відгуку
    """

    def has_object_permission(self, request, view, obj):
        # Читання дозволено всім
        if request.method in permissions.SAFE_METHODS:
            return True

        # Редагування тільки автору або адміну
        return obj.customer == request.user or request.user.is_admin()


class IsListingOwnerOrReadOnly(permissions.BasePermission):
    """
    Дозволяє читання всім, дії тільки власнику оголошення
    Використовується для відповіді власника на відгук
    """

    def has_object_permission(self, request, view, obj):
        # Читання дозволено всім
        if request.method in permissions.SAFE_METHODS:
            return True

        # Дії тільки для власника оголошення або адміна
        return obj.listing.owner == request.user or request.user.is_admin()


class CanCreateReviewAsCustomer(permissions.BasePermission):
    """Дозволяє створювати відгуки клієнтам, а адміну — все"""

    def has_permission(self, request, view):
        # читання всім
        if request.method in permissions.SAFE_METHODS:
            return True

        # ✅ адмін може все
        user = request.user
        if user.is_authenticated and (user.is_staff or user.is_superuser or user.is_admin()):
            return True

        # POST: тільки клієнт (не owner)
        if request.method == 'POST':
            return user.is_authenticated and not user.is_owner()

        # інші методи: тільки авторизовані
        return user.is_authenticated

class IsAdminOrOwner(permissions.BasePermission):
    """Доступ тільки адміну або власнику (owner)."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        is_admin = bool(
            user.is_staff or user.is_superuser or getattr(user, "is_admin", lambda: False)()
        )
        is_owner = bool(getattr(user, "is_owner", lambda: False)())

        return is_admin or is_owner
