

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.auth import is_admin

from apps.bookings.models import Booking, BookingStatus


def _as_date(dt):
    if dt is None:
        return None

    return dt if hasattr(dt, "year") and not hasattr(dt, "hour") else dt.date()


def _require_owner_or_admin(*, booking: Booking, actor):
    if is_admin(actor):
        return
    owner = getattr(booking.listing, "owner", None)
    if owner != actor:
        raise DjangoValidationError("Only listing owner or admin can perform this action.")


def _require_reviewer_or_owner_or_admin(*, booking: Booking, actor):

    if is_admin(actor):
        return
    if booking.customer == actor:
        return
    owner = getattr(booking.listing, "owner", None)
    if owner == actor:
        return
    raise DjangoValidationError("Forbidden.")


def _model_field_names(instance) -> set[str]:
    return {f.name for f in instance._meta.get_fields() if hasattr(f, "attname")}

def _safe_save(instance, fields: list[str]):
    """
    Зберігає тільки ті поля, які реально існують у моделі (DB fields).
    Якщо після фільтрації нічого не лишилось — робимо звичайний save().
    """
    allowed = _model_field_names(instance)
    safe_fields = [f for f in fields if f in allowed]

    if safe_fields:
        instance.save(update_fields=safe_fields)
    else:
        instance.save()


@transaction.atomic
def approve_booking(*, booking: Booking, actor) -> Booking:
    """
    PENDING -> CONFIRMED
    """
    _require_owner_or_admin(booking=booking, actor=actor)

    if booking.status != BookingStatus.PENDING:
        raise DjangoValidationError("Only pending bookings can be approved.")

    booking.status = BookingStatus.CONFIRMED
    booking.approved_at = timezone.now() if hasattr(booking, "approved_at") else None


    _safe_save(booking, ["status", "approved_at", "updated_at"])

    return booking


@transaction.atomic
def reject_booking(*, booking: Booking, actor, reason: str | None = None) -> Booking:
    """
    PENDING -> REJECTED
    """
    _require_owner_or_admin(booking=booking, actor=actor)

    if booking.status != BookingStatus.PENDING:
        raise DjangoValidationError("Only pending bookings can be rejected.")

    booking.status = BookingStatus.REJECTED
    if hasattr(booking, "rejected_reason") and reason is not None:
        booking.rejected_reason = reason
    if hasattr(booking, "rejected_at"):
        booking.rejected_at = timezone.now()

    _safe_save(booking, ["status", "rejected_reason", "rejected_at", "updated_at"])

    return booking


@transaction.atomic
def cancel_booking(*, booking: Booking, actor, reason: str | None = None) -> Booking:
    """
    CUSTOMER/OWNER/ADMIN: PENDING|CONFIRMED -> CANCELLED
    Забороняємо cancel якщо бронювання вже почалось (check_in <= today).
    """
    _require_reviewer_or_owner_or_admin(booking=booking, actor=actor)

    if booking.status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED):
        raise DjangoValidationError("This booking cannot be cancelled in the current status.")

    today = timezone.localdate()

    check_in = _as_date(getattr(booking, "check_in", None))
    if check_in and check_in <= today:
        raise DjangoValidationError("You cannot cancel a booking that has already started.")

    booking.status = BookingStatus.CANCELLED
    if hasattr(booking, "cancelled_at"):
        booking.cancelled_at = timezone.now()

    # хто скасував (якщо поля є)
    if hasattr(booking, "cancelled_by_id"):
        booking.cancelled_by = actor
    if hasattr(booking, "cancellation_reason") and reason is not None:
        booking.cancellation_reason = reason


    _safe_save(booking, ["status", "cancelled_at", "cancelled_by", "cancellation_reason", "updated_at"])

    return booking


@transaction.atomic
def complete_booking(*, booking: Booking, actor) -> Booking:
    """
    OWNER/ADMIN: CONFIRMED -> COMPLETED
    Зазвичай дозволяємо тільки після check_out <= today.
    """
    _require_owner_or_admin(booking=booking, actor=actor)

    if booking.status != BookingStatus.CONFIRMED:
        raise DjangoValidationError("Only confirmed bookings can be completed.")

    today = timezone.localdate()
    check_out = _as_date(getattr(booking, "check_out", None))

    if check_out and check_out > today:
        raise DjangoValidationError("You can complete a booking only after check-out date.")

    booking.status = BookingStatus.COMPLETED
    if hasattr(booking, "completed_at"):
        booking.completed_at = timezone.now()


    _safe_save(booking, ["status", "completed_at", "updated_at"])

    return booking


