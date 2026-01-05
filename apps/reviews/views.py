from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import models
from apps.common.auth import is_admin, is_owner


from django.contrib.auth import get_user_model

from .permissions import CanCreateReviewAsCustomer, IsAdminOrOwner


from .models import Review, ListingRating, OwnerRating
from .serializers import (
    ReviewSerializer,
    ReviewListSerializer,
    ListingRatingSerializer,
    OwnerRatingSerializer,
    OwnerResponseSerializer
)
from .services.strict_reviewers import compute_strict_reviewers
from apps.listings.models import Listing


class ReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet для відгуків

    list: Список всіх відгуків користувача
    create: Створити новий відгук
    retrieve: Деталі відгуку
    update/partial_update: Оновити відгук
    destroy: Видалити відгук
    respond: Відповісти на відгук (тільки власник оголошення)
    """

    queryset = Review.objects.select_related(
        'reviewer',
        'listing',
        'booking'
    ).all()
    serializer_class = ReviewSerializer
    permission_classes = [CanCreateReviewAsCustomer]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['rating', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = super().get_queryset()

        # базова логіка доступу
        if self.request.user.is_authenticated:
            queryset = queryset.filter(
                models.Q(reviewer=self.request.user) |
                models.Q(is_visible=True) |
                models.Q(listing__owner=self.request.user)
            )
        else:
            queryset = queryset.filter(is_visible=True)

        # ✅ ФІЛЬТР ПО РЕЙТИНГУ
        rating = self.request.query_params.get('rating')
        if rating:
            try:
                queryset = queryset.filter(rating=int(rating))
            except ValueError:
                pass

        return queryset

    def perform_create(self, serializer):
        """Створення відгуку"""
        serializer.save(reviewer=self.request.user)

    def _is_admin(self, user):
        return is_admin(user)

    def perform_update(self, serializer):
        user = self.request.user
        if serializer.instance.reviewer != user and not self._is_admin(user):
            raise permissions.PermissionDenied("You can only edit your own reviews")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.reviewer != user and not self._is_admin(user):
            raise permissions.PermissionDenied("You can only delete your own reviews")
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def respond(self, request, pk=None):
        """
        Відповісти на відгук (тільки власник оголошення)

        POST /api/reviews/{id}/respond/
        {
            "owner_response": "Thank you for your feedback!"
        }
        """
        review = self.get_object()

        # Перевірити що користувач - власник оголошення АБО адмін
        if review.listing.owner != request.user and not self._is_admin(request.user):
            return Response(
                {'detail': 'Only the listing owner or an admin can respond to reviews'},
                status=status.HTTP_403_FORBIDDEN
            )

        if review.rating is None:
            return Response(
                {'detail': 'Owner responses are available after a rating has been posted'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Валідувати відповідь
        serializer = OwnerResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Оновити відгук
        review.owner_response = serializer.validated_data['owner_response']
        review.owner_response_at = timezone.now()
        review.save()

        return Response(
            ReviewSerializer(review, context={'request': request}).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['delete'], permission_classes=[permissions.IsAuthenticated])
    def remove_response(self, request, pk=None):
        """
        Видалити відповідь власника

        DELETE /api/reviews/{id}/remove_response/
        """
        review = self.get_object()

        # Перевірити що користувач - власник оголошення АБО адмін
        if review.listing.owner != request.user and not self._is_admin(request.user):
            return Response(
                {'detail': 'Only the listing owner or an admin can remove responses'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Видалити відповідь
        review.owner_response = ''
        review.owner_response_at = None
        review.save()

        return Response(
            {'detail': 'Response removed successfully'},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_path='my')
    def my_reviews(self, request):
        user = request.user

        if not user.is_authenticated:
            return Response(
                {'detail': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        queryset = self.get_queryset().filter(reviewer=user)
        serializer = ReviewListSerializer(
            queryset,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)




class ListingReviewsView(APIView):
    """
    Список відгуків для конкретного оголошення

    GET /api/listings/{listing_id}/reviews/

    Query параметри:
    - rating: фільтр по рейтингу (1-5)
    - sort: сортування (newest, oldest, highest, lowest)
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, listing_id):
        """Отримати список відгуків"""
        # Перевірити що оголошення існує
        listing = get_object_or_404(Listing, id=listing_id)

        # Отримати відгуки
        reviews = Review.objects.filter(
            listing=listing,
            is_visible=True
        ).select_related('reviewer')

        # Фільтр по рейтингу
        rating_filter = request.query_params.get('rating')
        if rating_filter:
            try:
                rating_filter = int(rating_filter)
                reviews = reviews.filter(rating=rating_filter)
            except ValueError:
                pass

        # Сортування
        sort_param = request.query_params.get('sort', 'newest')
        if sort_param == 'newest':
            reviews = reviews.order_by('-created_at')
        elif sort_param == 'oldest':
            reviews = reviews.order_by('created_at')
        elif sort_param == 'highest':
            reviews = reviews.order_by('-rating', '-created_at')
        elif sort_param == 'lowest':
            reviews = reviews.order_by('rating', '-created_at')
        else:
            reviews = reviews.order_by('-created_at')

        # Серіалізувати
        serializer = ReviewListSerializer(
            reviews,
            many=True,
            context={'request': request}
        )

        return Response({
            'count': reviews.count(),
            'results': serializer.data
        })


class ListingRatingView(APIView):
    """
    Статистика рейтингу оголошення

    GET /api/listings/{listing_id}/rating/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, listing_id):
        """Отримати рейтинг оголошення"""
        # Перевірити що оголошення існує
        listing = get_object_or_404(Listing, id=listing_id)

        # Отримати або створити рейтинг
        try:
            rating_stats = ListingRating.objects.get(listing=listing)
        except ListingRating.DoesNotExist:
            # Створити рейтинг якщо не існує
            ListingRating.update_rating(listing_id)
            rating_stats = ListingRating.objects.get(listing=listing)

        # Серіалізувати
        serializer = ListingRatingSerializer(
            rating_stats,
            context={'request': request}
        )

        return Response(serializer.data)


class MyReviewsView(APIView):
    """
    Мої відгуки

    GET /api/reviews/my/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Отримати всі свої відгуки"""
        reviews = Review.objects.filter(
            reviewer=request.user
        ).select_related('listing', 'booking').order_by('-created_at')

        serializer = ReviewSerializer(
            reviews,
            many=True,
            context={'request': request}
        )

        return Response({
            'count': reviews.count(),
            'results': serializer.data
        })


class TopRatedListingsView(APIView):
    """
    Топ оголошень за рейтингом

    GET /api/listings/top-rated/

    Query параметри:
    - limit: кількість оголошень (default: 10)
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """Отримати топ оголошень"""
        limit = int(request.query_params.get('limit', 10))

        # Отримати оголошення з найвищим рейтингом
        top_ratings = ListingRating.objects.filter(
            total_reviews__gte=3  # Мінімум 3 відгуки
        ).select_related('listing').order_by(
            '-average_rating',
            '-total_reviews'
        )[:limit]

        serializer = ListingRatingSerializer(
            top_ratings,
            many=True,
            context={'request': request}
        )

        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })


class OwnerRatingView(APIView):
    """
    Статистика рейтингу власника

    GET /api/owners/{owner_id}/rating/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, owner_id):
        """Отримати рейтинг власника"""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Перевірити що власник існує
        owner = get_object_or_404(User, id=owner_id)

        # Отримати або створити рейтинг
        try:
            rating_stats = OwnerRating.objects.get(owner=owner)
        except OwnerRating.DoesNotExist:
            # Створити рейтинг якщо не існує
            OwnerRating.update_rating(owner_id)
            try:
                rating_stats = OwnerRating.objects.get(owner=owner)
            except OwnerRating.DoesNotExist:
                # Якщо немає відгуків - повернути порожній рейтинг
                return Response({
                    'owner_id': owner_id,
                    'owner_username': owner.username,
                    'owner_name': f"{owner.first_name} {owner.last_name}".strip() or owner.username,
                    'average_rating': '0.00',
                    'total_reviews': 0,
                    'total_listings': 0,
                    'stars_5': 0,
                    'stars_4': 0,
                    'stars_3': 0,
                    'stars_2': 0,
                    'stars_1': 0,
                    'rating_distribution': {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
                })

        # Серіалізувати
        serializer = OwnerRatingSerializer(
            rating_stats,
            context={'request': request}
        )

        return Response(serializer.data)


class TopRatedOwnersView(APIView):
    """
    Топ власників за рейтингом

    GET /api/owners/top-rated/

    Query параметри:
    - limit: кількість власників (default: 10)
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """Отримати топ власників"""
        limit = int(request.query_params.get('limit', 10))

        # Отримати власників з найвищим рейтингом
        top_ratings = OwnerRating.objects.filter(
            total_reviews__gte=3  # Мінімум 3 відгуки
        ).select_related('owner').order_by(
            '-average_rating',
            '-total_reviews'
        )[:limit]

        serializer = OwnerRatingSerializer(
            top_ratings,
            many=True,
            context={'request': request}
        )

        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })





class StrictReviewersAnalyticsView(APIView):
    permission_classes = [IsAdminOrOwner]

    def get(self, request):
        user = request.user
        User = get_user_model()

        def _to_int(name, default, min_value=1, max_value=1000):
            raw = request.query_params.get(name)
            if not raw:
                return default
            try:
                val = int(raw)
            except ValueError:
                return default
            return max(min_value, min(max_value, val))

        min_reviews = _to_int('min_reviews', 10, 1, 1000)
        min_other_reviews = _to_int('min_other_reviews', 2, 1, 1000)
        limit = _to_int('limit', 50, 1, 500)

        direction = request.query_params.get('direction', 'strict')  # strict | lenient | all
        if direction not in ('strict', 'lenient', 'all'):
            direction = 'strict'

        is_admin_user = is_admin(user)
        is_owner_user = is_owner(user)

        if not is_admin_user and not is_owner_user:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        base_qs = Review.objects.select_related('reviewer', 'listing')
        base_qs = base_qs.exclude(reviewer__is_staff=True).exclude(reviewer__is_superuser=True)

        scope = 'all'
        if not is_admin_user and is_owner_user:
            owner_listing_ids = Listing.objects.filter(owner_id=user.id).values_list('id', flat=True)
            base_qs = base_qs.filter(listing_id__in=owner_listing_ids)
            scope = 'owner'

        rows = compute_strict_reviewers(
            base_qs=base_qs,
            min_reviews=min_reviews,
            min_other_reviews=min_other_reviews,
            limit=limit,
        )

        # ✅ direction-фільтр
        if direction == 'strict':
            rows = [r for r in rows if r['harshness_index'] < 0]
        elif direction == 'lenient':
            rows = [r for r in rows if r['harshness_index'] > 0]

        reviewer_ids = [r['reviewer_id'] for r in rows]
        users_map = {
            u.id: u
            for u in User.objects.filter(id__in=reviewer_ids).only('id', 'username', 'first_name', 'last_name')
        }

        results = []
        for r in rows:
            u = users_map.get(r['reviewer_id'])
            confidence = min(1.0, r['reviews_used'] / float(min_reviews)) if min_reviews else 1.0

            results.append({
                **r,
                'confidence': round(confidence, 3),
                'reviewer_username': getattr(u, 'username', None),
                'reviewer_name': (
                    (f"{u.first_name} {u.last_name}".strip() if u else '') or getattr(u, 'username', None)
                ),
            })

        return Response({
            'scope': scope,
            'direction': direction,
            'min_reviews': min_reviews,
            'min_other_reviews': min_other_reviews,
            'limit': limit,
            'count': len(results),
            'results': results,
        })


# ════════════════════════════════════════════════════════════════════
# ПРИМІТКИ
# ════════════════════════════════════════════════════════════════════

"""
ENDPOINTS:
──────────────────────────────────────────────────────────────────────

ReviewViewSet:
    GET    /api/reviews/                    - Список своїх відгуків
    POST   /api/reviews/                    - Створити відгук
    GET    /api/reviews/{id}/               - Деталі відгуку
    PATCH  /api/reviews/{id}/               - Оновити відгук
    DELETE /api/reviews/{id}/               - Видалити відгук
    POST   /api/reviews/{id}/respond/       - Відповісти (власник)
    DELETE /api/reviews/{id}/remove_response/ - Видалити відповідь

Listing views:
    GET /api/listings/{id}/reviews/         - Відгуки оголошення
    GET /api/listings/{id}/rating/          - Рейтинг оголошення
    GET /api/listings/top-rated/            - Топ оголошень

Owner views:
    GET /api/owners/{id}/rating/            - Рейтинг власника
    GET /api/owners/top-rated/              - Топ власників

Other:
    GET /api/reviews/my/                    - Мої відгуки
"""
