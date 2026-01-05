from rest_framework import serializers
from apps.common.enums import BookingStatus
from .models import Booking
from apps.listings.models import Listing, ListingPhoto
from apps.listings.serializers import LocationSerializer as ListingLocationSerializer
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError


class ListingSerializer(serializers.ModelSerializer):
    """Мінімальна інформація про оголошення для бронювання"""

    main_photo = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            'id',
            'title',
            'property_type',
            'city',
            'address',
            'price',
            'main_photo'
        ]

    def get_main_photo(self, obj):
        photo = obj.photos.filter(is_main=True).first()
        if photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(photo.image.url)
        return None

    def get_city(self, obj):
        return obj.location.city if obj.location else None

    def get_address(self, obj):
        return obj.location.address if obj.location else None


class BookingSerializer(serializers.ModelSerializer):
    """Serializer для перегляду бронювань"""

    listing = ListingSerializer(read_only=True)
    location = ListingLocationSerializer(read_only=True)
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)
    customer_email = serializers.CharField(source='customer.email', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'listing',
            'location',
            'customer',
            'customer_name',
            'customer_email',
            'check_in',
            'check_out',
            'num_guests',
            'total_price',
            'status',
            'cancellation_reason',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['customer', 'location', 'total_price', 'created_at', 'updated_at']


class BookingListSerializer(serializers.ModelSerializer):
    """Serializer для списку бронювань (коротка інформація)"""

    listing_title = serializers.CharField(source='listing.title', read_only=True)
    listing_city = serializers.SerializerMethodField()
    location = ListingLocationSerializer(read_only=True)
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'listing_title',
            'listing_city',
            'location',
            'customer_name',
            'check_in',
            'check_out',
            'num_guests',
            'total_price',
            'status',
            'created_at'
        ]

    def get_listing_city(self, obj):
        return obj.location.city if obj.location else None


class BookingCreateSerializer(serializers.ModelSerializer):
    """Serializer для створення бронювання"""

    class Meta:
        model = Booking
        fields = [
            'listing',
            'check_in',
            'check_out',
            'num_guests'
        ]

    def validate(self, data):
        """Валідація дат та доступності"""
        check_in = data.get('check_in')
        check_out = data.get('check_out')
        listing = data.get('listing')

        # Перевірка що check_out після check_in
        if check_out <= check_in:
            raise serializers.ValidationError(
                "Дата виїзду повинна бути пізніше дати заїзду"
            )

        # Перевірка кількості гостей
        num_guests = data.get('num_guests', 1)
        if num_guests > listing.max_guests:
            raise serializers.ValidationError(
                f"Максимальна кількість гостей: {listing.max_guests}"
            )

        # Перевірка що оголошення активне
        if not listing.is_active or listing.is_deleted:
            raise serializers.ValidationError(
                "Це оголошення недоступне для бронювання"
            )

        # Перевірка що дати не зайняті
        overlapping = Booking.objects.filter(
            listing=listing,
            status__in=['PENDING', 'CONFIRMED'],
            check_in__lt=check_out,
            check_out__gt=check_in
        ).exists()

        if overlapping:
            raise serializers.ValidationError(
                "Ці дати вже заброньовані"
            )

        data['location'] = listing.location
        return data

    def create(self, validated_data):
        listing = validated_data['listing']
        check_in = validated_data['check_in']
        check_out = validated_data['check_out']

        num_days = (check_out - check_in).days
        total_price = listing.price * num_days

        try:
            booking = Booking.objects.create(
                total_price=total_price,
                **validated_data  # location вже тут
            )
        except DjangoValidationError as e:
            # Перетворюємо model ValidationError → DRF ValidationError (400)
            if hasattr(e, "message_dict"):
                raise DRFValidationError(e.message_dict)
            raise DRFValidationError({"detail": e.messages})

        return booking


class BookingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        # ✅ ДОДАЛИ можливість міняти дати/гостей + (за потреби) статус/причину
        fields = [
            'check_in',
            'check_out',
            'num_guests',
            'status',
            'cancellation_reason',
        ]

    def validate(self, attrs):
        """
        ✅ Бізнес-логіка: дати/гостей можна змінювати лише поки бронювання не стартувало
        і не є завершеним/скасованим.
        (За потреби правила можна послабити/змінити.)
        """
        booking: Booking = self.instance
        if not booking:
            return attrs

        # Якщо змінюють дати/гостей
        changes_dates_or_guests = any(
            k in attrs for k in ('check_in', 'check_out', 'num_guests')
        )

        if changes_dates_or_guests:
            # Забороняємо, якщо бронювання вже “закрите”
            if booking.status in [BookingStatus.CANCELLED, BookingStatus.COMPLETED]:
                raise serializers.ValidationError(
                    {"detail": "Cannot change dates/guests for cancelled or completed booking."}
                )

            # Забороняємо, якщо бронювання вже почалося (за бажанням)
            today = booking.created_at.date() if False else None  # заглушка, не використовуємо
            # краще:
            from django.utils import timezone
            if booking.check_in and booking.check_in <= timezone.now().date():
                raise serializers.ValidationError(
                    {"detail": "Cannot change dates/guests for a booking that has already started."}
                )

        return attrs

    def update(self, instance, validated_data):
        # ✅ застосовуємо зміни
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # ✅ перетворюємо Django ValidationError → DRF ValidationError (400 замість 500)
        try:
            instance.save()  # у тебе всередині save() викликається full_clean()
        except DjangoValidationError as e:
            if hasattr(e, "message_dict"):
                raise DRFValidationError(e.message_dict)
            raise DRFValidationError({"detail": e.messages})

        return instance


