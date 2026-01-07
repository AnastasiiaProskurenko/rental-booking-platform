from django.test import TestCase
from django.core.exceptions import ValidationError

from apps.common.tests.factories import make_user, make_listing, make_booking
from apps.common.enums import UserRole, BookingStatus
from apps.reviews.models import Review


class ReviewModelTests(TestCase):
    def test_review_create_for_completed_booking(self):
        owner = make_user(email="o@demo.local", role=UserRole.OWNER)
        customer = make_user(email="c@demo.local", role=UserRole.CUSTOMER)
        listing = make_listing(owner=owner)
        booking = make_booking(listing=listing, customer=customer, status=BookingStatus.COMPLETED)

        r = Review(booking=booking, listing=listing, reviewer=customer, rating=5, comment="Everything was great!")
        r.full_clean()
        r.save()
        self.assertEqual(Review.objects.count(), 1)
