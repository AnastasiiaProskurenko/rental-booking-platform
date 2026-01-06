from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from faker import Faker
from datetime import timedelta
from django.utils import timezone
import random
from decimal import Decimal

from apps.listings.models import Listing
from apps.bookings.models import Booking
from apps.reviews.models import Review
from apps.common.enums import PropertyType, CancellationPolicy
from apps.common.models import Location
from apps.common.constants import (
    MIN_BOOKING_DURATION_DAYS,
    MAX_BOOKING_DURATION_DAYS,
    MIN_DAYS_BEFORE_CHECKIN,
    MAX_DAYS_BEFORE_CHECKIN,
)
from apps.common.enums import BookingStatus

# IMPORTANT: підкоригуй імпорт під свій додаток payments
from apps.payments.models import Payment, PaymentStatus  # <-- перевір шлях

User = get_user_model()
fake = Faker(['en_US'])


class Command(BaseCommand):
    help = 'Generate fake data for testing (users/listings/bookings/reviews/payments)'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=20)
        parser.add_argument('--listings', type=int, default=50)
        parser.add_argument('--bookings', type=int, default=30)
        parser.add_argument('--reviews', type=int, default=20)
        parser.add_argument('--password', type=str, default='1111')
        parser.add_argument('--clear', action='store_true')

        parser.add_argument(
            '--mixed-booking-statuses',
            action='store_true',
            help='If set, bookings will use mixed statuses. If not set, only COMPLETED/CANCELLED are used.'
        )

        parser.add_argument(
            '--payments',
            type=int,
            default=None,
            help='How many payments to create. Default: equals bookings count (1 payment per booking).'
        )

        parser.add_argument(
            '--seed',
            type=int,
            default=None,
            help='Optional random seed for repeatable generation.'
        )

    def handle(self, *args, **options):
        if options['seed'] is not None:
            random.seed(options['seed'])
            Faker.seed(options['seed'])

        if options['clear']:
            self.stdout.write('Clearing data...')
            # порядок важливий (FK)
            Review.objects.all().delete()
            Payment.objects.all().delete()
            Booking.objects.all().delete()
            Listing.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        with transaction.atomic():
            self.faker = fake
            self.stdout.write('Generating fake data...')

            groups = self.create_groups()
            users = self.generate_users(options['users'], options['password'], groups)
            self.stdout.write(f'✓ {len(users)} users')

            listings = self.generate_listings(options['listings'], users)
            self.stdout.write(f'✓ {len(listings)} listings')

            bookings = self.generate_bookings(
                options['bookings'],
                users,
                listings,
                mixed_statuses=options['mixed_booking_statuses'],
            )
            self.stdout.write(f'✓ {len(bookings)} bookings')

            payments_count = options['payments'] if options['payments'] is not None else len(bookings)
            payments = self.generate_payments(payments_count, bookings)
            self.stdout.write(f'✓ {len(payments)} payments')

            reviews = self.generate_reviews(options['reviews'], bookings)
            self.stdout.write(f'✓ {len(reviews)} reviews')

        self.stdout.write(self.style.SUCCESS('\n✅ Done!'))
        self.stdout.write(f'Password for all users: {options["password"]}')

    def create_groups(self):
        groups = {}
        for name in ['Customers', 'Owners', 'Admins']:
            groups[name], _ = Group.objects.get_or_create(name=name)
        return groups

    def generate_users(self, count, password, groups):
        users = []
        for i in range(count):
            rand = random.random()
            if rand < 0.30:
                user_type, group = 'owner', groups['Owners']
            elif rand < 0.95:
                user_type, group = 'customer', groups['Customers']
            else:
                user_type, group = 'admin', groups['Admins']

            user = User.objects.create_user(
                username=f"{user_type}_{i + 1}",
                email=f"{user_type}_{i + 1}@example.com",
                password=password,
                first_name=fake.first_name(),
                last_name=fake.last_name()
            )
            user.groups.add(group)
            users.append(user)
        return users

    def generate_listings(self, count, users):
        listings = []
        owners = [u for u in users if u.groups.filter(name='Owners').exists()] or users

        for _ in range(count):
            owner = random.choice(owners)

            location, _ = Location.objects.get_or_create(
                country=self.faker.country(),
                city=self.faker.city(),
                address=self.faker.street_address(),
            )

            listing = Listing.objects.create(
                owner=owner,
                title=self.faker.sentence(nb_words=6),
                description=self.faker.text(max_nb_chars=300),
                location=location,

                property_type=random.choice([c[0] for c in PropertyType.choices]),

                num_rooms=random.randint(1, 5),
                num_bedrooms=random.randint(1, 4),
                num_bathrooms=random.randint(1, 3),
                max_guests=random.randint(1, 6),

                area=Decimal(random.randint(30, 150)),
                price=Decimal(random.randint(30, 300)),
                cleaning_fee=Decimal(random.randint(0, 50)),

                cancellation_policy=random.choice([c[0] for c in CancellationPolicy.choices]),

                is_hotel_apartment=False,
                is_active=True,
                is_verified=True,
            )

            listings.append(listing)

        return listings

    def generate_bookings(self, count, users, listings, mixed_statuses: bool = False):
        customers = [u for u in users if u.groups.filter(name='Customers').exists()] or users
        bookings = []

        today = timezone.now().date()
        min_checkin = today + timedelta(days=MIN_DAYS_BEFORE_CHECKIN)
        max_checkin = today + timedelta(days=MAX_DAYS_BEFORE_CHECKIN)

        if not mixed_statuses:
            all_statuses = [BookingStatus.COMPLETED, BookingStatus.CANCELLED]
        else:
            all_statuses = [
                BookingStatus.PENDING,
                BookingStatus.CONFIRMED,
                BookingStatus.IN_PROGRESS,
                BookingStatus.COMPLETED,
                BookingStatus.CANCELLED,
            ]

        # Ось твоя бізнес-логіка:
        # - PENDING може перетинатися
        # - CONFIRMED/IN_PROGRESS НЕ мають перетинатися між собою
        exclusive_statuses = {
            BookingStatus.CONFIRMED,
            BookingStatus.IN_PROGRESS,
        }

        def is_slot_free_for_exclusive(listing, start, end) -> bool:
            return not Booking.objects.filter(
                listing=listing,
                status__in=list(exclusive_statuses),
                check_in__lt=end,
                check_out__gt=start,
            ).exists()

        max_attempts = 500

        for _ in range(count):
            listing = random.choice(listings)

            customer_pool = [c for c in customers if c != listing.owner] or customers
            customer = random.choice(customer_pool)

            status = random.choice(all_statuses)

            chosen_check_in = None
            chosen_check_out = None

            for _attempt in range(max_attempts):
                check_in = fake.date_between(start_date=min_checkin, end_date=max_checkin)
                nights = random.randint(MIN_BOOKING_DURATION_DAYS, MAX_BOOKING_DURATION_DAYS)
                check_out = check_in + timedelta(days=nights)

                # Перевіряємо тільки якщо статус ексклюзивний
                if status in exclusive_statuses and not is_slot_free_for_exclusive(listing, check_in, check_out):
                    continue

                chosen_check_in = check_in
                chosen_check_out = check_out
                break

            if chosen_check_in is None:
                continue

            booking = Booking.objects.create(
                listing=listing,
                customer=customer,
                location=listing.location,
                check_in=chosen_check_in,
                check_out=chosen_check_out,
                num_guests=random.randint(1, min(listing.max_guests, 6)),
                status=status,
            )
            bookings.append(booking)

        return bookings

    def generate_payments(self, count, bookings):
        """
        1 payment per booking by default.
        Якщо count > len(bookings) — випадково дублюємо booking-и (як повторні транзакції),
        але в більшості систем краще 1:1.
        """
        if not bookings or count <= 0:
            return []

        payments = []

        def model_has_field(model_cls, field_name: str) -> bool:
            return any(f.name == field_name for f in model_cls._meta.get_fields())

        def booking_total_amount(b: Booking) -> Decimal:
            # адаптуй формулу, якщо у тебе інша логіка ціни
            nights = max((b.check_out - b.check_in).days, 1)
            base = (b.listing.price * Decimal(nights)) + (b.listing.cleaning_fee or Decimal('0'))
            return base

        def choose_payment_status_for_booking(b: Booking) -> str:
            # Мапінг логічний, але з рандомом
            if b.status == BookingStatus.COMPLETED:
                return random.choices(
                    [PaymentStatus.COMPLETED, PaymentStatus.PROCESSING, PaymentStatus.PENDING, PaymentStatus.FAILED],
                    weights=[85, 5, 7, 3],
                    k=1
                )[0]

            if b.status == BookingStatus.CANCELLED:
                return random.choices(
                    [PaymentStatus.REFUNDED, PaymentStatus.CANCELLED, PaymentStatus.FAILED, PaymentStatus.PENDING],
                    weights=[60, 25, 10, 5],
                    k=1
                )[0]

            if b.status == BookingStatus.IN_PROGRESS:
                return random.choices(
                    [PaymentStatus.PROCESSING, PaymentStatus.COMPLETED, PaymentStatus.PENDING, PaymentStatus.FAILED],
                    weights=[55, 25, 15, 5],
                    k=1
                )[0]

            if b.status == BookingStatus.CONFIRMED:
                return random.choices(
                    [PaymentStatus.PENDING, PaymentStatus.PROCESSING, PaymentStatus.COMPLETED, PaymentStatus.FAILED],
                    weights=[45, 35, 15, 5],
                    k=1
                )[0]

            # PENDING booking
            return random.choices(
                [PaymentStatus.PENDING, PaymentStatus.PROCESSING, PaymentStatus.FAILED, PaymentStatus.CANCELLED],
                weights=[60, 20, 15, 5],
                k=1
            )[0]

        pool = bookings[:]
        for _ in range(count):
            b = random.choice(pool)

            status = choose_payment_status_for_booking(b)
            amount = booking_total_amount(b)

            payload = {}

            # найтиповіші поля
            if model_has_field(Payment, 'booking'):
                payload['booking'] = b
            if model_has_field(Payment, 'amount'):
                payload['amount'] = amount
            if model_has_field(Payment, 'status'):
                payload['status'] = status

            # optional fields (заповнюємо тільки якщо існують)
            if model_has_field(Payment, 'user'):
                payload['user'] = b.customer
            if model_has_field(Payment, 'customer'):
                payload['customer'] = b.customer
            if model_has_field(Payment, 'listing'):
                payload['listing'] = b.listing
            if model_has_field(Payment, 'currency'):
                payload['currency'] = 'USD'
            if model_has_field(Payment, 'provider'):
                payload['provider'] = random.choice(['stripe', 'paypal', 'test'])
            if model_has_field(Payment, 'reference'):
                payload['reference'] = self.faker.uuid4()

            # paid_at / completed_at: ставимо тільки для COMPLETED/REFUNDED
            now = timezone.now()
            if status in [PaymentStatus.COMPLETED, PaymentStatus.REFUNDED]:
                if model_has_field(Payment, 'paid_at'):
                    payload['paid_at'] = now - timedelta(minutes=random.randint(1, 60 * 24 * 30))
                if model_has_field(Payment, 'completed_at'):
                    payload['completed_at'] = now - timedelta(minutes=random.randint(1, 60 * 24 * 30))

            payments.append(Payment.objects.create(**payload))

        return payments

    def generate_reviews(self, count, bookings):
        completed = [b for b in bookings if b.status == BookingStatus.COMPLETED]
        if not completed:
            return []

        reviews = []
        used = set()

        for _ in range(min(count, len(completed))):
            booking = random.choice([b for b in completed if b.id not in used])
            used.add(booking.id)

            has_rating = random.choice([True, False])
            has_comment = random.choice([True, False])

            if not has_rating and not has_comment:
                has_rating = True

            rating = random.randint(3, 5) if has_rating else None
            comment = fake.text(200) if has_comment else ""

            reviews.append(
                Review.objects.create(
                    booking=booking,
                    listing=booking.listing,
                    reviewer=booking.customer,
                    rating=rating,
                    comment=comment,
                )
            )

        return reviews
