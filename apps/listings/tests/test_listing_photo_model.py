from django.test import TestCase
from django.core.files.base import ContentFile
from apps.listings.models import Listing, ListingPhoto
from apps.common.models import Location
from django.contrib.auth import get_user_model

User = get_user_model()

class ListingPhotoTest(TestCase):

    def test_only_one_main_photo(self):
        user = User.objects.create_user(email="p@test.com", username="p", password="1234")
        location = Location.objects.create(country="DE", city="Berlin", address="X")
        listing = Listing.objects.create(
            owner=user,
            title="Test",
            description="Test",
            location=location,
            property_type="APARTMENT",
            num_rooms=1,
            num_bathrooms=1,
            max_guests=2,
            price=50
        )

        png = ContentFile(b"123", name="a.png")
        ListingPhoto.objects.create(listing=listing, image=png, is_main=True)

        with self.assertRaises(Exception):
            ListingPhoto.objects.create(listing=listing, image=png, is_main=True)
