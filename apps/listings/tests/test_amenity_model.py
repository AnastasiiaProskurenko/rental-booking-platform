from django.test import TestCase
from apps.listings.models import Amenity

class AmenityTest(TestCase):

    def test_unique_name(self):
        Amenity.objects.create(name="Wi-Fi")

        with self.assertRaises(Exception):
            Amenity.objects.create(name="Wi-Fi")
