from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date, timedelta
from apps.bookings.models import Booking
from apps.common.enums import BookingStatus
from apps.listings.models import Listing
from apps.common.models import Location

User = get_user_model()

class BookingModelTest(TestCase):

    def test_total_price_calculated(self):
        owner = User.objects.create_user(email="o@test.com", username="o", password="1234")
        customer = User.objects.create_user(email="c@test.com", username="c", password="1234")
        location = Location.objects.create(country="DE", city="Berlin", address="X")

        listing = Listing.objects.create(
            owner=owner,
            title="Flat",
            description="Flat",
            location=location,
            property_type="APARTMENT",
            num_rooms=1,
            num_bathrooms=1,
            max_guests=2,
            price=100
        )

        booking = Booking(
            listing=listing,
            customer=customer,
            location=location,
            check_in=date.today(),
            check_out=date.today() + timedelta(days=3),
            num_guests=2,
            status=BookingStatus.COMPLETED
        )

        booking.clean()
        booking.save()

        self.assertIsNotNone(booking.total_price)
