from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from faker import Faker
from django.core.files.base import ContentFile
from apps.common.constants import (
    MIN_BOOKING_DURATION_DAYS,
    MAX_BOOKING_DURATION_DAYS,
    MIN_DAYS_BEFORE_CHECKIN,
    MAX_DAYS_BEFORE_CHECKIN,
)
from apps.common.enums import BookingStatus, PropertyType, CancellationPolicy,UserRole
from apps.common.models import Location
from apps.users.models import UserProfile

from apps.listings.models import Listing, ListingPhoto, Amenity
from apps.bookings.models import Booking
from apps.reviews.models import Review
from apps.payments.models import Payment, PaymentStatus




User = get_user_model()


def _model_has_field(model_cls, field_name: str) -> bool:
    return any(f.name == field_name for f in model_cls._meta.get_fields())


class Command(BaseCommand):
    help = "Seed data for local/dev (users/listings/bookings/payments/reviews + optional notifications/search)."

    def add_arguments(self, parser):
        parser.add_argument("--purge", action="store_true", help="Delete seeded data before creating new.")
        parser.add_argument("--seed", type=int, default=None, help="Random seed for repeatable generation.")
        parser.add_argument("--password", type=str, default="1111", help="Password for created users.")

        parser.add_argument("--admins", type=int, default=1)
        parser.add_argument("--owners", type=int, default=10)
        parser.add_argument("--users", type=int, default=60)

        parser.add_argument("--listings", type=int, default=80)
        parser.add_argument("--bookings", type=int, default=200)
        parser.add_argument("--payments", type=int, default=150)
        parser.add_argument("--reviews", type=int, default=60)

        parser.add_argument("--notifications", type=int, default=120)
        parser.add_argument("--search-queries", type=int, default=120)
        parser.add_argument("--listing-views", type=int, default=0)

        parser.add_argument(
            "--mixed-booking-statuses",
            action="store_true",
            help="If set, bookings will use mixed statuses; else only COMPLETED/CANCELLED.",
        )

    def handle(self, *args, **opts):
        if opts["seed"] is not None:
            random.seed(opts["seed"])
            Faker.seed(opts["seed"])

        self.faker = Faker(["en_US"])

        with transaction.atomic():
            if opts["purge"]:
                self._purge()

            # -------------------- users + profiles --------------------
            admins = self._create_users(
                count=opts["admins"],
                password=opts["password"],
                role=UserRole.ADMIN,
                prefix="admin",
                make_staff=True,
            )
            owners = self._create_users(
                count=opts["owners"],
                password=opts["password"],
                role=UserRole.OWNER,
                prefix="owner",
                make_staff=False,
            )
            customers = self._create_users(
                count=opts["users"],
                password=opts["password"],
                role=UserRole.CUSTOMER,
                prefix="user",
                make_staff=False,
            )
            all_users = admins + owners + customers

            profiles_created = self._create_user_profiles(all_users)

            # -------------------- listings + amenities + photos --------------------
            listings = self._create_listings(opts["listings"], owners)

            amenities_created = 0
            amenities_links = 0
            try:
                amenities = self._ensure_amenities()
                amenities_created = len(amenities)
                amenities_links = self._assign_amenities_to_listings(listings, amenities)
            except Exception:
                # якщо методів/моделі немає — просто пропустимо
                pass

            photos_created = 0
            try:
                photos_created = self._create_listing_photos(listings)
            except Exception:
                pass

            # -------------------- bookings -> payments -> reviews --------------------
            bookings = self._create_bookings(
                opts["bookings"],
                customers=customers,
                listings=listings,
                mixed_statuses=opts["mixed_booking_statuses"],
            )

            payments = self._create_payments(opts["payments"], bookings)
            reviews = self._create_reviews(opts["reviews"], bookings)

            # -------------------- optional apps --------------------
            notif_created = self._create_notifications_if_available(opts["notifications"], all_users)
            search_created = self._create_search_if_available(opts["search_queries"], all_users)

            if opts.get("listing_views") and opts["listing_views"] > 0:
                self.stdout.write(self.style.WARNING(
                    "Listing views seeding is not implemented yet (no model wired)."
                ))

        self.stdout.write(self.style.SUCCESS("✅ seed_data finished successfully"))
        self.stdout.write(f"Password for created users: {opts['password']}")
        self.stdout.write(
            "Created: "
            f"admins={len(admins)}, owners={len(owners)}, users={len(customers)}, "
            f"profiles={profiles_created}, "
            f"listings={len(listings)}, amenities={amenities_created}, amenities_links={amenities_links}, "
            f"photos={photos_created}, "
            f"bookings={len(bookings)}, payments={len(payments)}, reviews={len(reviews)}, "
            f"notifications={notif_created}, search_queries={search_created}"
        )

    # -------------------- purge --------------------

    def _purge(self):
        # 1) залежні від listings
        try:
            ListingPhoto.objects.all().delete()
        except Exception:
            pass

        # 2) відгуки/платежі/бронювання
        for model in (Review, Payment, Booking):
            try:
                model.objects.all().delete()
            except Exception:
                pass

        # 3) listings
        try:
            Listing.objects.all().delete()
        except Exception:
            pass

        # 4) m2m та довідники
        try:
            Amenity.objects.all().delete()
        except Exception:
            pass

        # 5) профілі
        try:
            UserProfile.objects.all().delete()
        except Exception:
            pass

        # 6) locations
        try:
            Location.objects.all().delete()
        except Exception:
            pass

        # 7) users (не чіпаємо суперюзерів)
        try:
            User.objects.filter(is_superuser=False).delete()
        except Exception:
            pass

        self._purge_optional()
        self.stdout.write("Purged core data (incl profiles/photos/amenities).")

    def _purge_optional(self):
        try:
            from apps.notifications.models import Notification
            Notification.objects.all().delete()
        except Exception:
            pass

        try:
            from apps.search.models import SearchHistory
            SearchHistory.objects.all().delete()
        except Exception:
            pass

    # -------------------- groups/users --------------------

    def _ensure_groups(self):
        groups = {}
        for name in ["Customers", "Owners", "Admins"]:
            groups[name], _ = Group.objects.get_or_create(name=name)
        return groups

    def _create_users(self, *, count: int, password: str, role: str, prefix: str, make_staff: bool = False):
        users = []

        for i in range(count):
            email = f"{prefix}{i + 1}@demo.local"
            username = f"{prefix}{i + 1}"

            u = User.objects.filter(email=email).first()
            if not u:
                u = User.objects.create_user(
                    email=email,
                    username=username,
                    password=password,
                    first_name=self.faker.first_name(),
                    last_name=self.faker.last_name(),
                )

            #  ключове: виставляємо role
            if hasattr(u, "role"):
                u.role = role

            if make_staff:
                u.is_staff = True

            u.save()
            users.append(u)

        return users



    # optional: UserProfile
    # def _ensure_profile(self, u: User):
    #     from apps.users.models import UserProfile
    #     UserProfile.objects.get_or_create(
    #         user=u,
    #         defaults={
    #             "country": self.faker.country(),
    #             "city": self.faker.city(),
    #             "phone": None,
    #             "languages": "de",
    #         },
    #     )

    # -------------------- listings --------------------

    def _create_listings(self, count: int, owners: list[User]):
        listings: list[Listing] = []

        for i in range(count):
            owner = random.choice(owners)

            #  гарантуємо унікальність адреси
            unique_suffix = self.faker.unique.bothify(text="??##??##")
            address = f"{self.faker.street_address()}, {unique_suffix}"

            location = Location.objects.create(
                country=self.faker.country(),
                city=self.faker.city(),
                address=address,
            )

            listing = Listing(
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

            #  запускаємо твою валідацію
            listing.full_clean()
            listing.save()
            listings.append(listing)

        return listings

    def _ensure_amenities(self) -> list[Amenity]:
        preset = [
            ("Wi-Fi", "wifi"),
            ("Parking", "parking"),
            ("Air conditioning", "ac"),
            ("Kitchen", "kitchen"),
            ("Washing machine", "washer"),
            ("Heating", "heating"),
            ("TV", "tv"),
            ("Elevator", "elevator"),
            ("Balcony", "balcony"),
        ]

        out: list[Amenity] = []
        for name, icon in preset:
            a, _ = Amenity.objects.get_or_create(
                name=name,
                defaults={"icon": icon, "description": self.faker.sentence(nb_words=10)},
            )
            out.append(a)
        return out

    def _assign_amenities_to_listings(self, listings: list[Listing], amenities: list[Amenity]) -> int:
        links = 0
        for listing in listings:
            k = random.randint(3, min(7, len(amenities)))
            selected = random.sample(amenities, k)
            listing.amenities.set(selected)
            links += k
        return links

    def _fake_png_bytes(self) -> bytes:
        # 1x1 transparent PNG
        return (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\x0d\n\x2d\xb4"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def _create_listing_photos(self, listings: list[Listing], min_photos: int = 3, max_photos: int = 6) -> int:
        created = 0
        png = self._fake_png_bytes()

        for listing in listings:
            photos_count = random.randint(min_photos, max_photos)

            for idx in range(photos_count):
                is_main = (idx == 0)

                photo = ListingPhoto(
                    listing=listing,
                    caption=self.faker.sentence(nb_words=6),
                    order=idx,
                    is_main=is_main,
                )
                filename = f"seed_{listing.pk}_{idx}.png"
                photo.image.save(filename, ContentFile(png), save=False)

                photo.full_clean()  #  перевірить unique_main_photo_per_listing
                photo.save()
                created += 1

        return created
    # -------------------- bookings --------------------

    def _create_bookings(
        self,
        count: int,
        *,
        customers: list[User],
        listings: list[Listing],
        mixed_statuses: bool,
    ) -> list[Booking]:
        bookings: list[Booking] = []

        today = timezone.now().date()
        min_checkin = today + timedelta(days=MIN_DAYS_BEFORE_CHECKIN)
        max_checkin = today + timedelta(days=MAX_DAYS_BEFORE_CHECKIN)

        all_statuses = (
            [
                BookingStatus.PENDING,
                BookingStatus.CONFIRMED,
                BookingStatus.IN_PROGRESS,
                BookingStatus.COMPLETED,
                BookingStatus.CANCELLED,
            ]
            if mixed_statuses
            else [BookingStatus.COMPLETED, BookingStatus.CANCELLED]
        )

        exclusive_statuses = {BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS}

        def is_slot_free_for_exclusive(listing: Listing, start, end) -> bool:
            return not Booking.objects.filter(
                listing=listing,
                status__in=list(exclusive_statuses),
                check_in__lt=end,
                check_out__gt=start,
            ).exists()

        max_attempts = 500
        errors_shown = 0
        errors_total = 0

        for _ in range(count):
            listing = random.choice(listings)

            customer_pool = [c for c in customers if c != listing.owner] or customers
            customer = random.choice(customer_pool)

            status = random.choice(all_statuses)

            chosen_check_in = None
            chosen_check_out = None

            for _attempt in range(max_attempts):
                check_in = self.faker.date_between(start_date=min_checkin, end_date=max_checkin)
                nights = random.randint(MIN_BOOKING_DURATION_DAYS, MAX_BOOKING_DURATION_DAYS)
                check_out = check_in + timedelta(days=nights)

                if status in exclusive_statuses and not is_slot_free_for_exclusive(listing, check_in, check_out):
                    continue

                chosen_check_in = check_in
                chosen_check_out = check_out
                break

            if chosen_check_in is None:
                continue

            booking = Booking(
                listing=listing,
                customer=customer,
                location=listing.location,
                check_in=chosen_check_in,
                check_out=chosen_check_out,
                num_guests=random.randint(1, min(listing.max_guests, 6)),
                status=status,
            )

            try:
                # ВАЖЛИВО: спочатку clean() (бо там _calculate_prices), потім full_clean()
                booking.clean()
                booking.full_clean()
                booking.save()
                bookings.append(booking)

            except Exception as e:
                errors_total += 1
                if errors_shown < 5:
                    self.stdout.write(self.style.WARNING(f"[booking skipped] {e}"))
                    errors_shown += 1
                continue

        if errors_total:
            self.stdout.write(self.style.WARNING(f"Bookings skipped due to validation errors: {errors_total}"))

        return bookings

    # -------------------- payments --------------------

    def _money(self, val) -> Decimal:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _map_booking_status_to_payment_status(self, booking_status: str) -> str:
        """
        ВИМОГА: Booking.payment_status == Payment.status (1:1)
        Тому робимо детермінований мапінг.
        Після цього ще оновимо Booking.payment_status при створенні Payment.
        """
        mapping = {
            BookingStatus.PENDING: PaymentStatus.PENDING,
            BookingStatus.CONFIRMED: PaymentStatus.PROCESSING,
            BookingStatus.IN_PROGRESS: PaymentStatus.PROCESSING,
            BookingStatus.COMPLETED: PaymentStatus.COMPLETED,
            BookingStatus.CANCELLED: PaymentStatus.CANCELLED,
        }
        return mapping.get(booking_status, PaymentStatus.PENDING)

    def _create_payments(self, count: int, bookings: list[Booking]) -> list[Payment]:
        if not bookings or count <= 0:
            return []

        payments: list[Payment] = []

        # беремо тільки унікальні bookings
        unique_bookings = list({b.pk: b for b in bookings}.values())

        # відкидаємо ті, де Payment вже існує (якщо раптом запуск без --purge)
        bookings_without_payment = [b for b in unique_bookings if not Payment.objects.filter(booking=b).exists()]

        if not bookings_without_payment:
            return []

        target = min(count, len(bookings_without_payment))
        random.shuffle(bookings_without_payment)
        selected = bookings_without_payment[:target]

        for b in selected:
            b.refresh_from_db(fields=["total_price", "status"])

            if b.total_price is None:
                continue

            payment_status = self._map_booking_status_to_payment_status(b.status)
            amount = self._money(b.total_price)

            payload: dict = {}

            if _model_has_field(Payment, "booking"):
                payload["booking"] = b
            if _model_has_field(Payment, "amount"):
                payload["amount"] = amount
            if _model_has_field(Payment, "status"):
                payload["status"] = payment_status

            if _model_has_field(Payment, "user"):
                payload["user"] = b.customer
            if _model_has_field(Payment, "customer"):
                payload["customer"] = b.customer
            if _model_has_field(Payment, "listing"):
                payload["listing"] = b.listing
            if _model_has_field(Payment, "currency"):
                payload["currency"] = "USD"
            if _model_has_field(Payment, "provider"):
                payload["provider"] = random.choice(["stripe", "paypal", "test"])
            if _model_has_field(Payment, "reference"):
                payload["reference"] = self.faker.uuid4()

            now = timezone.now()
            if payment_status in [PaymentStatus.COMPLETED, PaymentStatus.REFUNDED]:
                if _model_has_field(Payment, "paid_at"):
                    payload["paid_at"] = now - timedelta(minutes=random.randint(1, 60 * 24 * 30))
                if _model_has_field(Payment, "completed_at"):
                    payload["completed_at"] = now - timedelta(minutes=random.randint(1, 60 * 24 * 30))

            p = Payment.objects.create(**payload)
            payments.append(p)

            # СИНХРОНІЗАЦІЯ: якщо Booking має payment_status — ставимо таке ж як у Payment
            if _model_has_field(Booking, "payment_status"):
                try:
                    Booking.objects.filter(pk=b.pk).update(payment_status=payment_status)
                except Exception:
                    pass

        return payments

    # -------------------- reviews --------------------

    def _create_reviews(self, count: int, bookings: list[Booking]) -> list[Review]:
        completed = [b for b in bookings if b.status == BookingStatus.COMPLETED]
        if not completed:
            return []

        reviews: list[Review] = []
        used: set[int] = set()

        for _ in range(min(count, len(completed))):
            candidates = [b for b in completed if b.id not in used]
            if not candidates:
                break

            booking = random.choice(candidates)
            used.add(booking.id)

            has_rating = random.choice([True, False])
            has_comment = random.choice([True, False])
            if not has_rating and not has_comment:
                has_rating = True

            rating = random.randint(3, 5) if has_rating else None
            comment = self.faker.text(200) if has_comment else ""

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

    # -------------------- optional: notifications/search --------------------

    def _create_notifications_if_available(self, count: int, users: list[User]) -> int:
        if count <= 0:
            return 0
        try:
            from apps.notifications.models import Notification
        except Exception:
            return 0

        created = 0
        for _ in range(count):
            u = random.choice(users)
            payload = {}

            if _model_has_field(Notification, "user"):
                payload["user"] = u
            elif _model_has_field(Notification, "recipient"):
                payload["recipient"] = u

            if _model_has_field(Notification, "title"):
                payload["title"] = self.faker.sentence(nb_words=6)[:120]
            if _model_has_field(Notification, "message"):
                payload["message"] = self.faker.text(220)

            Notification.objects.create(**payload)
            created += 1

        return created

    def _create_search_if_available(self, count: int, users: list[User]) -> int:
        if count <= 0:
            return 0
        try:
            from apps.search.models import SearchHistory
        except Exception:
            return 0

        created = 0
        for _ in range(count):
            u = random.choice(users)
            payload = {}

            if _model_has_field(SearchHistory, "user"):
                payload["user"] = u
            if _model_has_field(SearchHistory, "query"):
                payload["query"] = random.choice([self.faker.city(), self.faker.country(), self.faker.word()])

            SearchHistory.objects.create(**payload)
            created += 1

        return created

    def _create_user_profiles(self, users: list[User]) -> int:
        created = 0
        for u in users:
            if UserProfile.objects.filter(user=u).exists():
                continue

            UserProfile.objects.create(
                user=u,
                country=self.faker.country(),
                city=self.faker.city(),
                phone=self.faker.phone_number()[:30],
                biography=self.faker.text(200),
                languages=random.choice(["de", "en", "en,de"]),
            )
            created += 1
        return created



