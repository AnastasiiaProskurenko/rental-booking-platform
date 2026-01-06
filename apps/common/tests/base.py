
from django.test import TestCase
from faker import Faker

class BaseModelTestCase(TestCase):
    faker = Faker("en_US")
