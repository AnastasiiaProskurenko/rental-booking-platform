

from django.utils import timezone

from apps.bookings.models import Booking
from apps.common.enums import BookingStatus
from apps.common.auth import is_admin


def bookings_base_qs(*, user):
    """
    Базовий queryset з доступом:
    - admin: всі
    - owner: лише свої listing
    - customer: лише свої бронювання
    """
    qs = Booking.objects.select_related("listing", "customer", "location")

    if not user or not user.is_authenticated:
        return qs.none()

    if is_admin(user):
        return qs

    if getattr(user, "is_owner", lambda: False)():
        return qs.filter(listing__owner=user)

    return qs.filter(customer=user)


def upcoming_bookings_qs(*, user):
    """
    Upcoming = check_in >= today AND статус у PENDING/CONFIRMED/IN_PROGRESS (за потреби)
    """
    today = timezone.now().date()
    return bookings_base_qs(user=user).filter(
        check_in__gte=today,
        status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS],
    )


def current_bookings_qs(*, user):
    """
    Current = check_in <= today < check_out AND статус CONFIRMED або IN_PROGRESS
    """
    today = timezone.now().date()
    return bookings_base_qs(user=user).filter(
        check_in__lte=today,
        check_out__gt=today,
        status__in=[BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS],
    )


def past_bookings_qs(*, user):
    """
    Past = check_out < today (все, що завершилось у минулому)
    """
    today = timezone.now().date()
    return bookings_base_qs(user=user).filter(
        check_out__lt=today
    )
