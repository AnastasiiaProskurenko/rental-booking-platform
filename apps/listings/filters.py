import django_filters
from .models import Listing


class ListingFilter(django_filters.FilterSet):
    # -----------------------------
    # LOCATION
    # -----------------------------
    country = django_filters.CharFilter(
        field_name="location__country",
        lookup_expr="iexact"
    )

    city = django_filters.CharFilter(
        field_name="location__city",
        lookup_expr="iexact"
    )

    # -----------------------------
    # PRICE
    # -----------------------------
    min_price = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="gte"
    )
    max_price = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="lte"
    )

    # -----------------------------
    # COMMON
    # -----------------------------
    owner = django_filters.NumberFilter(field_name="owner_id")
    is_active = django_filters.BooleanFilter(field_name="is_active")

    # -----------------------------
    # PROPERTY TYPE
    # -----------------------------
    property_type = django_filters.CharFilter(
        field_name="property_type",
        lookup_expr="iexact"
    )

    # -----------------------------
    # AREA (sq.m.)
    # -----------------------------
    min_area = django_filters.NumberFilter(
        field_name="area",
        lookup_expr="gte"
    )
    max_area = django_filters.NumberFilter(
        field_name="area",
        lookup_expr="lte"
    )

    # -----------------------------
    # GUESTS
    # -----------------------------
    guests = django_filters.NumberFilter(
        field_name="max_guests",
        lookup_expr="exact"
    )
    min_guests = django_filters.NumberFilter(
        field_name="max_guests",
        lookup_expr="gte"
    )
    max_guests = django_filters.NumberFilter(
        field_name="max_guests",
        lookup_expr="lte"
    )

    # -----------------------------
    # ROOMS / BEDROOMS / BATHROOMS
    # -----------------------------
    rooms = django_filters.NumberFilter(
        field_name="num_rooms",
        lookup_expr="exact"
    )
    min_rooms = django_filters.NumberFilter(
        field_name="num_rooms",
        lookup_expr="gte"
    )
    max_rooms = django_filters.NumberFilter(
        field_name="num_rooms",
        lookup_expr="lte"
    )

    bedrooms = django_filters.NumberFilter(
        field_name="num_bedrooms",
        lookup_expr="exact"
    )
    min_bedrooms = django_filters.NumberFilter(
        field_name="num_bedrooms",
        lookup_expr="gte"
    )
    max_bedrooms = django_filters.NumberFilter(
        field_name="num_bedrooms",
        lookup_expr="lte"
    )

    bathrooms = django_filters.NumberFilter(
        field_name="num_bathrooms",
        lookup_expr="exact"
    )
    min_bathrooms = django_filters.NumberFilter(
        field_name="num_bathrooms",
        lookup_expr="gte"
    )
    max_bathrooms = django_filters.NumberFilter(
        field_name="num_bathrooms",
        lookup_expr="lte"
    )

    # -----------------------------
    # AMENITIES (by icon)
    # -----------------------------
    amenities = django_filters.CharFilter(method="filter_amenities_any")
    amenities_all = django_filters.CharFilter(method="filter_amenities_all")

    def _parse_icons(self, value: str) -> list[str]:
        return [v.strip().lower() for v in (value or "").split(",") if v.strip()]

    def filter_amenities_any(self, queryset, name, value):
        icons = self._parse_icons(value)
        if not icons:
            return queryset
        return queryset.filter(
            amenities__icon__in=icons
        ).distinct()

    def filter_amenities_all(self, queryset, name, value):
        icons = self._parse_icons(value)
        if not icons:
            return queryset
        for icon in icons:
            queryset = queryset.filter(amenities__icon=icon)
        return queryset.distinct()

    class Meta:
        model = Listing
        fields = [
            # location
            "country",
            "city",

            # price
            "min_price",
            "max_price",

            # common
            "owner",
            "is_active",

            # listing params
            "property_type",
            "min_area",
            "max_area",
            "guests",
            "min_guests",
            "max_guests",
            "rooms",
            "min_rooms",
            "max_rooms",
            "bedrooms",
            "min_bedrooms",
            "max_bedrooms",
            "bathrooms",
            "min_bathrooms",
            "max_bathrooms",

            # amenities
            "amenities",
            "amenities_all",
        ]