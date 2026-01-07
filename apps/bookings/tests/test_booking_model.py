from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.bookings.models import Booking
from apps.listings.models import Listing
from apps.common.models import Location
from apps.common.enums import BookingStatus, PropertyType, CancellationPolicy
from django.contrib.auth import get_user_model

User = get_user_model()

class BookingModelTest(TestCase):
    def test_total_price_calculated(self):
        owner = User.objects.create_user(email="o@test.com", username="o", password="1111")
        customer = User.objects.create_user(email="c@test.com", username="c", password="1111")

        location = Location.objects.create(country="DE", city="Berlin", address="Street 1")

        listing = Listing.objects.create(
            owner=owner,
            title="Test listing",
            description="Test description",
            location=location,
            property_type=PropertyType.APARTMENT,
            num_rooms=1,
            num_bedrooms=1,
            num_bathrooms=1,
            max_guests=2,
            area=Decimal("50.00"),
            price=Decimal("100.00"),
            cleaning_fee=Decimal("10.00"),
            cancellation_policy=CancellationPolicy.MODERATE,
            is_hotel_apartment=False,
            is_active=True,
            is_verified=True,
        )

        today = timezone.now().date()
        booking = Booking(
            listing=listing,
            customer=customer,
            location=location,
            check_in=today + timedelta(days=5),
            check_out=today + timedelta(days=7),
            num_guests=1,
            status=BookingStatus.PENDING,
        )

        booking.clean()  # запускає _calculate_prices()

        self.assertIsNotNone(booking.total_price)
        self.assertGreater(booking.total_price, Decimal("0.00"))