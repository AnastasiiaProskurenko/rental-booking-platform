from rest_framework import serializers
from .models import Payment, Refund
from apps.users.serializers import UserSerializer
from apps.bookings.models import Booking


class PaymentSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)

    # booking у відповіді (read-only)
    booking = serializers.PrimaryKeyRelatedField(read_only=True)

    # booking_id на вхід, але записуємо в поле booking
    booking_id = serializers.PrimaryKeyRelatedField(
        queryset=Booking.objects.all(),
        source='booking',
        write_only=True
    )

    class Meta:
        model = Payment
        fields = (
            'id',
            'booking', 'booking_id',
            'customer',
            'amount',
            'payment_method',
            'status',
            'transaction_id',
            'payment_date',
            'notes',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'booking',
            'customer',
            'status',
            'transaction_id',
            'payment_date',
            'created_at',
            'updated_at',
        )




class RefundSerializer(serializers.ModelSerializer):
    payment = PaymentSerializer(read_only=True)
    processed_by = UserSerializer(read_only=True)

    # payment_id на вхід (FK), записуємо у поле payment
    payment_id = serializers.PrimaryKeyRelatedField(
        queryset=Payment.objects.all(),
        source='payment',
        write_only=True
    )

    class Meta:
        model = Refund
        fields = (
            'id',
            'payment', 'payment_id',
            'amount',
            'reason',
            'status',
            'transaction_id',
            'refund_date',
            'processed_by',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'payment',
            'status',
            'processed_by',
            'refund_date',
            'transaction_id',
            'created_at',
            'updated_at',
        )

