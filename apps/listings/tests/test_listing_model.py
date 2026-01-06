from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.listings.models import Listing
from apps.common.models import Location
from apps.common.enums import PropertyType

User = get_user_model()

class ListingModelTest(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@test.com",
            username="owner",
            password="1234"
        )
        self.location = Location.objects.create(
            country="Germany",
            city="Berlin",
            address="Test str 1"
        )

    def test_listing_creation(self):
        listing = Listing.objects.create(
            owner=self.owner,
            title="Nice flat",
            description="Test",
            location=self.location,
            property_type=PropertyType.APARTMENT,
            num_rooms=2,
            num_bathrooms=1,
            max_guests=3,
            price=100
        )

        self.assertEqual(listing.owner, self.owner)

    def test_address_uniqueness(self):
        Listing.objects.create(
            owner=self.owner,
            title="A",
            description="A",
            location=self.location,
            property_type=PropertyType.APARTMENT,
            num_rooms=2,
            num_bathrooms=1,
            max_guests=3,
            price=100
        )

        with self.assertRaises(Exception):
            Listing.objects.create(
                owner=self.owner,
                title="B",
                description="B",
                location=self.location,
                property_type=PropertyType.APARTMENT,
                num_rooms=2,
                num_bathrooms=1,
                max_guests=3,
                price=120
            )
