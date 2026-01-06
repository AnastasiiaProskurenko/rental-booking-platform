from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.users.models import UserProfile

User = get_user_model()

class UserProfileTest(TestCase):

    def test_profile_created(self):
        user = User.objects.create_user(
            email="p@example.com",
            username="p",
            password="1234"
        )

        profile = UserProfile.objects.create(
            user=user,
            country="Germany",
            city="Berlin"
        )

        self.assertEqual(profile.user, user)

    def test_listing_count_zero(self):
        user = User.objects.create_user(
            email="c@example.com",
            username="c",
            password="1234"
        )
        profile = UserProfile.objects.create(user=user)
        self.assertEqual(profile.listing_count, 0)
