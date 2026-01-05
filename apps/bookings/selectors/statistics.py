

from decimal import Decimal

from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.common.enums import BookingStatus
from apps.common.auth import is_admin


# ============================================================
# Scope helpers
# ============================================================

def bookings_base_qs(*, user):
    """
    Базовий queryset для статистики залежно від ролі користувача
    """
    qs = Booking.objects.all()

    if not user or not user.is_authenticated:
        return qs.none()

    # Admin → всі бронювання
    if is_admin(user):
        return qs

    # Owner → бронювання по його listing
    if getattr(user, "is_owner", lambda: False)():
        return qs.filter(listing__owner=user)

    # Customer → тільки свої бронювання
    return qs.filter(customer=user)


# ============================================================
# Main statistics selector
# ============================================================

def bookings_statistics(*, user) -> dict:
    """
    Агрегована статистика бронювань.
    Всі підрахунки виконуються через SQL.
    """

    today = timezone.now().date()
    qs = bookings_base_qs(user=user)

    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------
    total = qs.count()

    # --------------------------------------------------------
    # BY STATUS
    # --------------------------------------------------------
    status_counts = (
        qs.values("status")
        .annotate(count=Count("id"))
    )

    by_status_map = {row["status"]: row["count"] for row in status_counts}

    by_status = {
        "pending": by_status_map.get(BookingStatus.PENDING, 0),
        "confirmed": by_status_map.get(BookingStatus.CONFIRMED, 0),
        "in_progress": by_status_map.get(BookingStatus.IN_PROGRESS, 0),
        "completed": by_status_map.get(BookingStatus.COMPLETED, 0),
        "cancelled": by_status_map.get(BookingStatus.CANCELLED, 0),
        "rejected": by_status_map.get(BookingStatus.REJECTED, 0),
    }

    # --------------------------------------------------------
    # TIME-BASED
    # --------------------------------------------------------
    upcoming = qs.filter(check_in__gt=today).count()
    current = qs.filter(check_in__lte=today, check_out__gt=today).count()
    past = qs.filter(check_out__lte=today).count()

    # --------------------------------------------------------
    # FINANCIALS (ONLY COMPLETED)
    # --------------------------------------------------------
    completed_qs = qs.filter(status=BookingStatus.COMPLETED)

    financials = completed_qs.aggregate(
        revenue=Sum("total_price"),
        avg_price=Avg("total_price"),
    )

    revenue = financials["revenue"] or Decimal("0")
    avg_price = financials["avg_price"] or Decimal("0")

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------
    return {
        "total": total,

        "by_status": by_status,

        "timeline": {
            "upcoming": upcoming,
            "current": current,
            "past": past,
        },

        "finance": {
            "revenue": str(revenue),
            "avg_completed_price": str(avg_price),
        },
    }
