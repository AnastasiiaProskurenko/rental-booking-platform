from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.common.enums import UserRole

User = get_user_model()

class UserModelTest(TestCase):

    def test_create_user_with_role(self):
        user = User.objects.create_user(
            email="admin@example.com",
            username="adm",
            password="admin123",
            role=UserRole.OWNER
        )

        self.assertEqual(user.role, UserRole.OWNER)
        self.assertTrue(user.is_owner())
        self.assertFalse(user.is_customer())

    def test_email_is_unique(self):
        User.objects.create_user(
            email="unique@example.com",
            username="u1",
            password="1111"
        )

        with self.assertRaises(Exception):
            User.objects.create_user(
                email="unique@example.com",
                username="u2",
                password="1111"
            )
