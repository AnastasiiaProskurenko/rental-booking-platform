from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count

from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Notification
from .serializers import NotificationSerializer, NotificationUpdateSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['notification_type', 'is_read']
    search_fields = ['title', 'message']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        qs = Notification.objects.all()

        # Адмін/стаф бачить все
        if user.is_staff or user.is_superuser:
            return qs

        # Звичайний користувач — лише свої
        return qs.filter(user=user)

    def get_serializer_class(self):
        # Адмін/стаф можуть редагувати все
        if self.action in ['update', 'partial_update'] and (
                self.request.user.is_staff or self.request.user.is_superuser
        ):
            return NotificationSerializer

        # Звичайні користувачі — тільки is_read
        if self.action in ['update', 'partial_update']:
            return NotificationUpdateSerializer

        return NotificationSerializer

    def perform_create(self, serializer):
        user = self.request.user

        # Адмін може вказати user у body (бо у serializer fields="__all__")
        if (user.is_staff or user.is_superuser) and serializer.validated_data.get('user'):
            serializer.save()
            return

        # Інакше — створюємо тільки для себе
        serializer.save(user=user)
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):

        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):

        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'status': 'All notifications marked as read'})
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):

        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'Notification marked as read'})

    @action(detail=False, methods=['get'], url_path='by_type')
    def by_type(self, request):
        notification_type = request.query_params.get('notification_type')
        if not notification_type:
            return Response(
                {'error': 'notification_type query parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            limit = int(request.query_params.get('limit', 20))
            offset = int(request.query_params.get('offset', 0))
        except ValueError:
            return Response({'error': 'limit/offset must be integers.'}, status=400)

        qs = (
            self.get_queryset()
            .filter(notification_type=notification_type)
            .order_by('-created_at')
        )

        total = qs.count()
        items = qs[offset: offset + limit]
        serializer = self.get_serializer(items, many=True)

        next_offset = offset + limit
        next_url = None
        if next_offset < total:
            next_url = request.build_absolute_uri(
                f'?notification_type={notification_type}&limit={limit}&offset={next_offset}'
            )

        return Response({
            'notification_type': notification_type,
            'count': total,
            'next': next_url,
            'previous': None if offset == 0 else request.build_absolute_uri(
                f'?notification_type={notification_type}&limit={limit}&offset={max(0, offset - limit)}'
            ),
            'results': serializer.data
        })

    @action(detail=False, methods=['get'], url_path='grouped')
    def grouped(self, request):
        # N для кожного типу
        try:
            limit = int(request.query_params.get('limit', 5))
        except ValueError:
            return Response({'error': 'limit must be integer.'}, status=400)

        base_qs = self.get_queryset()

        # Зберемо counts по типах (тільки ті типи, які реально є в qs)
        counts = {
            row['notification_type']: row['count']
            for row in base_qs.values('notification_type').annotate(count=Count('id'))
        }

        # Якщо хочете показувати всі можливі типи навіть з 0 — треба брати choices з моделі.
        # Тут залишаю тільки ті, що є в БД для поточного qs.
        result = []

        for ntype, total in counts.items():
            qs = base_qs.filter(notification_type=ntype).order_by('-created_at')
            items = list(qs[:limit])
            serializer = self.get_serializer(items, many=True)

            has_more = total > limit
            next_url = None
            if has_more:
                # next веде на ваш by_type з offset=limit
                next_url = request.build_absolute_uri(
                    f'/api/notifications/by-type/?notification_type={ntype}&limit={limit}&offset={limit}'
                )

            result.append({
                'notification_type': ntype,
                'count': total,
                'limit': limit,
                'has_more': has_more,
                'next': next_url,
                'results': serializer.data,
            })

        # Опційно: стабільний порядок типів
        result.sort(key=lambda x: x['notification_type'])

        return Response({
            'limit_per_type': limit,
            'types': result
        })