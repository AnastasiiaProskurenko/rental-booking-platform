from rest_framework import permissions
from rest_framework.permissions import BasePermission


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        # Визначаємо "owner" для різних моделей
        owner = getattr(obj, "owner", None)

        # якщо це ListingPhoto (або будь-який об'єкт з listing)
        if owner is None and hasattr(obj, "listing"):
            owner = getattr(obj.listing, "owner", None)

        return (owner == request.user) or request.user.is_admin()


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Дозволяє читання всім, редагування тільки власнику (або адміну).
    Працює і для Listing (obj.owner), і для ListingPhoto (obj.listing.owner).
    """

    def has_object_permission(self, request, view, obj):
        # Read-only дозволено всім
        if request.method in permissions.SAFE_METHODS:
            return True

        # Визначаємо owner універсально
        owner = getattr(obj, "owner", None)
        if owner is None and hasattr(obj, "listing"):
            owner = getattr(obj.listing, "owner", None)

        return (owner == request.user) or request.user.is_admin()

class IsOwnerToCreate(permissions.BasePermission):
    """
    Створювати оголошення можуть тільки Owners та Admins
    """

    def has_permission(self, request, view):
        # Перегляд дозволено всім
        if request.method in permissions.SAFE_METHODS:
            return True

        # Створення тільки для Owners та Admins
        if request.method == 'POST':
            return request.user.is_authenticated and (
                request.user.is_owner() or request.user.is_admin()
            )

        # Інші небезпечні методи (PUT/PATCH/DELETE) вимагають автентифікації
        return request.user.is_authenticated


class IsOwnerRoleOrAdmin(permissions.BasePermission):
    """
    Дозволяє доступ тільки власникам та адміністраторам
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_owner() or request.user.is_admin()
        )
