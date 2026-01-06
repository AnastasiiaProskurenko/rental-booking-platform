from django.test import TestCase
from apps.payments.models import Payment
from apps.common.enums import PaymentStatus

class PaymentModelTest(TestCase):

    def test_payment_amount_positive(self):
        with self.assertRaises(Exception):
            Payment.objects.create(amount=-10, status=PaymentStatus.PENDING)
