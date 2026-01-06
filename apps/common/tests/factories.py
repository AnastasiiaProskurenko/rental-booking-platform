from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.common.models import Location
from apps.common.enums import UserRole, PropertyType, CancellationPolicy, BookingStatus
from apps.listings.models import Listing
from apps.bookings.models import Booking

User = get_user_model()


def make_user(*, email="u1@demo.local", role=UserRole.CUSTOMER, password="1111", **kwargs) -> User:
    u = User.objects.create_user(
        email=email,
        username=kwargs.pop("username", email.split("@")[0]),
        password=password,
        first_name=kwargs.pop("first_name", "John"),
        last_name=kwargs.pop("last_name", "Doe"),
        **kwargs
    )
    if hasattr(u, "role"):
        u.role = role
        u.save(update_fields=["role"])
    return u


def make_location(*, country="Germany", city="Berlin", address="Street 1") -> Location:
    return Location.objects.create(country=country, city=city, address=address)


def make_listing(*, owner: User, location: Location | None = None, **kwargs) -> Listing:
    location = location or make_location(address=f"Street {owner.id}")
    listing = Listing(
        owner=owner,
        title=kwargs.pop("title", "Nice apartment"),
        description=kwargs.pop("description", "Desc"),
        location=location,
        property_type=kwargs.pop("property_type", PropertyType.APARTMENT),
        num_rooms=kwargs.pop("num_rooms", 2),
        num_bedrooms=kwargs.pop("num_bedrooms", 1),
        num_bathrooms=kwargs.pop("num_bathrooms", 1),
        max_guests=kwargs.pop("max_guests", 2),
        area=kwargs.pop("area", Decimal("40")),
        price=kwargs.pop("price", Decimal("100")),
        cleaning_fee=kwargs.pop("cleaning_fee", Decimal("10")),
        cancellation_policy=kwargs.pop("cancellation_policy", CancellationPolicy.MODERATE),
        is_hotel_apartment=kwargs.pop("is_hotel_apartment", False),
        is_active=kwargs.pop("is_active", True),
        is_verified=kwargs.pop("is_verified", True),
        **kwargs,
    )
    listing.full_clean()
    listing.save()
    return listing


def make_booking(
    *,
    listing: Listing,
    customer: User,
    check_in: date | None = None,
    nights: int = 3,
    status=BookingStatus.PENDING,
    **kwargs
) -> Booking:
    today = timezone.now().date()
    check_in = check_in or (today + timedelta(days=10))
    check_out = check_in + timedelta(days=nights)

    b = Booking(
        listing=listing,
        customer=customer,
        location=listing.location,
        check_in=check_in,
        check_out=check_out,
        num_guests=kwargs.pop("num_guests", 1),
        status=status,
        **kwargs
    )
    # важливо: у тебе pricing рахується в clean()
    b.clean()
    b.full_clean()
    b.save()
    return b
