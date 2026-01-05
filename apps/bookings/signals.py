import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.bookings.models import Booking
from apps.common.enums import BookingStatus
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

STATUS_MESSAGES = {
    BookingStatus.PENDING: "очікує підтвердження",
    BookingStatus.CONFIRMED: "підтверджено",
    BookingStatus.CANCELLED: "скасовано",
    BookingStatus.COMPLETED: "завершено",
    BookingStatus.REJECTED: "відхилено",
    BookingStatus.IN_PROGRESS: "у процесі",
    BookingStatus.EXPIRED: "прострочено",
}


@receiver(pre_save, sender=Booking)
def store_previous_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return

    try:
        instance._previous_status = Booking.objects.only("status").get(pk=instance.pk).status
    except Booking.DoesNotExist:
        instance._previous_status = None


@receiver(post_save, sender=Booking)
def create_booking_notifications(sender, instance, created, **kwargs):
    if created:
        title_customer = "Нове бронювання"
        notif = Notification.objects.create(
            user=instance.customer,
            title=title_customer,
            message=f"Бронювання #{instance.pk} створено, чекайте підтвердження",
            notification_type="BOOKING",
            related_object_id=instance.pk,
            related_object_type="booking",
        )
        logger.info(
            "Notification created. notification_id=%s user_id=%s title=%s booking_id=%s",
            notif.id,
            instance.customer_id,
            title_customer,
            instance.id,
        )

        title_owner = "Новий запит на бронювання"
        notif2 = Notification.objects.create(
            user=instance.listing.owner,
            title=title_owner,
            message=f"Новий букінг #{instance.pk}, прийміть або скасуйте",
            notification_type="BOOKING",
            related_object_id=instance.pk,
            related_object_type="booking",
        )
        logger.info(
            "Notification created. notification_id=%s user_id=%s title=%s booking_id=%s",
            notif2.id,
            instance.listing.owner_id,
            title_owner,
            instance.id,
        )
        return

    previous_status = getattr(instance, "_previous_status", None)
    if previous_status is None or previous_status == instance.status:
        return

    status_message = STATUS_MESSAGES.get(instance.status, instance.get_status_display().lower())
    title = "Статус бронювання оновлено"

    notif = Notification.objects.create(
        user=instance.customer,
        title=title,
        message=f"Бронювання #{instance.pk} {status_message}.",
        notification_type="BOOKING",
        related_object_id=instance.pk,
        related_object_type="booking",
    )
    logger.info(
        "Notification created. notification_id=%s user_id=%s title=%s booking_id=%s from=%s to=%s",
        notif.id,
        instance.customer_id,
        title,
        instance.id,
        previous_status,
        instance.status,
    )
