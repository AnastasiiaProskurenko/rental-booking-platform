from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q, Count
from django.utils import timezone



from apps.bookings.services.status import (
    approve_booking,
    reject_booking,
    cancel_booking,
    complete_booking,
)

from .models import Booking
from .selectors.statistics import bookings_statistics
from apps.bookings.selectors.queries import (
    upcoming_bookings_qs,
    current_bookings_qs,
    past_bookings_qs,
)

from .serializers import (
    BookingSerializer,
    BookingListSerializer,
    BookingCreateSerializer,
    BookingUpdateSerializer

)
from .permissions import (
    IsCustomerOrListingOwnerOrAdmin,
    IsListingOwnerOrAdmin,
    IsCustomerRole,
)
from apps.common.enums import BookingStatus


class BookingViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управління бронюваннями

    list: GET /api/bookings/ - список бронювань
    retrieve: GET /api/bookings/{id}/ - деталі бронювання
    create: POST /api/bookings/ - створити бронювання
    update: PUT /api/bookings/{id}/ - оновити бронювання
    partial_update: PATCH /api/bookings/{id}/ - часткове оновлення
    destroy: DELETE /api/bookings/{id}/ - видалити бронювання
    """

    queryset = Booking.objects.select_related(
        'customer',
        'listing',
        'listing__owner',
        'listing__location',
        'location',

    ).all()

    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    # Фільтрація
    filterset_fields = {
        'status': ['exact', 'in'],
        'listing': ['exact'],
        'location': ['exact'],
        'customer': ['exact'],
        'check_in': ['gte', 'lte', 'exact'],
        'check_out': ['gte', 'lte', 'exact'],
        'num_guests': ['gte', 'lte', 'exact'],
        'total_price': ['gte', 'lte', 'exact'],
    }

    # Пошук
    search_fields = [
        'customer__email',
        'customer__first_name',
        'customer__last_name',
        'listing__title',
        'listing__location__city',
        'location__city',
        'location__address',
        'notes'
    ]

    # Сортування
    ordering_fields = [
        'created_at',
        'check_in',
        'check_out',
        'total_price',
        'status'
    ]
    ordering = ['-created_at']

    def get_serializer_class(self):
        """
        Вибір серіалізатора залежно від action
        """
        if self.action == 'list':
            return BookingListSerializer

        elif self.action == 'create':
            return BookingCreateSerializer

        elif self.action in ['update', 'partial_update']:
            return BookingUpdateSerializer

        elif self.action in ['approve', 'reject', 'cancel', 'complete', 'change_status']:
            return BookingUpdateSerializer

        return BookingSerializer

    def get_queryset(self):
        """
        Фільтрація queryset залежно від прав користувача
        """
        user = self.request.user
        queryset = super().get_queryset()

        # Адміни бачать всі бронювання
        if user.is_admin():
            return queryset

        # Owners бачать бронювання своїх оголошень + свої бронювання як клієнт
        if user.is_owner():
            return queryset.filter(
                Q(listing__owner=user) | Q(customer=user)
            )

        # Клієнти бачать тільки свої бронювання
        return queryset.filter(customer=user)

    def get_permissions(self):
        """
        Права доступу залежно від action
        """
        if self.action == 'create':
            return [permissions.IsAuthenticated(), IsCustomerRole()]

        if self.action in ['update', 'partial_update', 'destroy']:
            return [
                permissions.IsAuthenticated(),
                IsCustomerOrListingOwnerOrAdmin()
            ]

        elif self.action in ['approve', 'reject', 'complete']:
            return [
                permissions.IsAuthenticated(),
                IsListingOwnerOrAdmin()
            ]

        elif self.action == 'cancel':
            return [
                permissions.IsAuthenticated(),
                IsCustomerOrListingOwnerOrAdmin()
            ]

        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        """
        При створенні автоматично встановлюємо customer та created_by
        """
        serializer.save(
            customer=self.request.user
        )

    def perform_destroy(self, instance):
        """
        Видалення бронювання (тільки якщо статус WAITING)
        """
        if instance.status != BookingStatus.PENDING:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "Can only delete bookings with 'waiting' status"
            )

        instance.delete()

    # ============================================
    # CUSTOM ACTIONS - ФІЛЬТРИ
    # ============================================

    @action(detail=False, methods=['get'])
    def my_bookings(self, request):
        """
        Мої бронювання (як клієнт)
        GET /api/bookings/my_bookings/
        """
        queryset = self.get_queryset().filter(customer=request.user)
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = BookingListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = BookingListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_listing_bookings(self, request):
        """
        Бронювання моїх оголошень (як власник)
        GET /api/bookings/my_listing_bookings/
        """
        if not request.user.is_owner() and not request.user.is_admin():
            return Response(
                {'error': 'Only owners can view listing bookings'},
                status=status.HTTP_403_FORBIDDEN
            )

        queryset = self.get_queryset().filter(listing__owner=request.user)
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = BookingListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = BookingListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        qs = upcoming_bookings_qs(user=request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def current(self, request):
        qs = current_bookings_qs(user=request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def past(self, request):
        qs = past_bookings_qs(user=request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """
        Бронювання що очікують підтвердження
        GET /api/bookings/pending/
        Owner: pending для його listing
        Admin: всі pending в системі
        """
        if not request.user.is_owner() and not request.user.is_admin():
            return Response(
                {'error': 'Only owners can view pending bookings'},
                status=status.HTTP_403_FORBIDDEN
            )

        qs = self.get_queryset().filter(status=BookingStatus.PENDING)

        # ✅ тільки owner обмежуємо по своїх оголошеннях
        if request.user.is_owner() and not request.user.is_admin():
            qs = qs.filter(listing__owner=request.user)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = BookingListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = BookingListSerializer(qs, many=True)
        return Response(serializer.data)

    # ============================================
    # CUSTOM ACTIONS - ЗМІНА СТАТУСУ
    # ============================================

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        booking = self.get_object()

        try:
            booking = approve_booking(booking=booking, actor=request.user)
        except DjangoValidationError as e:
            raise DRFValidationError(e.messages)

        return Response(BookingSerializer(booking, context={"request": request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """
        Відхилити бронювання
        POST /api/bookings/{id}/reject/
        Body: {"reason": "..."} (optional)
        Тільки для власника оголошення або адміна
        """
        booking = self.get_object()

        if booking.status != BookingStatus.PENDING:
            return Response(
                {"error": 'Can only reject bookings with "waiting" status'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = (request.data.get("reason") or "").strip()

        try:
            booking = reject_booking(booking=booking, actor=request.user, reason=reason)
        except DjangoValidationError as e:
            raise DRFValidationError(e.messages)

        return Response(BookingSerializer(booking, context={"request": request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """
        Скасувати бронювання
        POST /api/bookings/{id}/cancel/
        Body: {"reason": "..."} (optional)
        Для клієнта або власника оголошення або адміна
        """
        booking = self.get_object()

        reason = request.data.get("reason")
        try:
            booking = cancel_booking(booking=booking, actor=request.user, reason=reason)
        except DjangoValidationError as e:
            raise DRFValidationError(e.messages)

        return Response(BookingSerializer(booking, context={"request": request}).data, status=status.HTTP_200_OK)



    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Завершити бронювання
        POST /api/bookings/{id}/complete/
        Тільки для власника оголошення або адміна
        """
        booking = self.get_object()

        try:
            booking = complete_booking(booking=booking, actor=request.user)
        except DjangoValidationError as e:
            raise DRFValidationError(e.messages)

        return Response(BookingSerializer(booking, context={"request": request}).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['patch'],
        permission_classes=[permissions.IsAuthenticated, IsListingOwnerOrAdmin]
    )
    def change_status(self, request, pk=None):
        """
        Змінити статус бронювання власником оголошення
        PATCH /api/bookings/{id}/change_status/
        Тіло: {"status": "confirmed" | "rejected" | "cancelled" | "completed"}
        """
        booking = self.get_object()

        serializer = BookingUpdateSerializer(
            booking,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['patch'])
    def reschedule(self, request, pk=None):
        booking = self.get_object()
        serializer = BookingUpdateSerializer(
            booking, data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(BookingSerializer(booking).data)

    # ============================================
    # CUSTOM ACTIONS - СТАТИСТИКА
    # ============================================

    @action(detail=False, methods=["get"])
    def statistics(self, request):
        data = bookings_statistics(user=request.user)
        return Response(data)

    @action(detail=True, methods=['get'])
    def can_review(self, request, pk=None):
        booking = self.get_object()

        # ✅ Дозволено customer або admin
        if request.user != booking.customer and not request.user.is_admin():
            return Response(
                {'error': 'Only customer or admin can check review availability'},
                status=status.HTTP_403_FORBIDDEN
            )

        can_review = (
                booking.status == BookingStatus.COMPLETED and
                booking.check_out < timezone.now().date()
        )

        has_review = hasattr(booking, 'review')

        return Response({
            'can_review': can_review and not has_review,
            'has_review': has_review,
            'booking_status': booking.status,
            'check_out': booking.check_out
        })


# ============================================
# ДОДАТКОВИЙ ViewSet для швидкого перегляду
# ============================================

class BookingCalendarViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для календаря бронювань
    Тільки для читання, показує зайняті дати
    """
    queryset = Booking.objects.filter(
        status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED]
    )
    serializer_class = BookingListSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @action(detail=False, methods=['get'])
    def by_listing(self, request):
        """
        Бронювання для конкретного оголошення (для календаря)
        GET /api/bookings/calendar/by_listing/?listing_id=123
        """
        listing_id = request.query_params.get('listing_id')

        if not listing_id:
            return Response(
                {'error': 'listing_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        bookings = self.queryset.filter(listing_id=listing_id)

        # Форматування для календаря
        calendar_data = []
        for booking in bookings:
            calendar_data.append({
                'id': booking.id,
                'start': booking.check_in,
                'end': booking.check_out,
                'status': booking.status,
                'customer_name': booking.customer.get_full_name(),
            })

        return Response(calendar_data)
