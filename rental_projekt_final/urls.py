from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.users.views import EmailTokenObtainPairView


# Один набір API роутів, який підключаємо двічі: /api/ та /api/v1/
api_patterns = [
    path('', include('apps.users.api_urls')),
    path('', include('apps.reviews.urls')),
    path('', include('apps.listings.urls')),
    path('', include('apps.bookings.urls')),
    path('', include('apps.notifications.urls')),
    path('', include('apps.payments.urls')),
    path('', include('apps.search.urls')),
    path('', include('apps.analytics.urls')),
]


urlpatterns = [
    # ============================================
    # HTML сторінки
    # ============================================
    path('', include('apps.users.urls')),

    # ============================================
    # Admin
    # ============================================
    path('admin/', admin.site.urls),

    # ============================================
    # JWT Auth
    # ============================================
    path('api/auth/token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ============================================
    # API Documentation (без версії)
    # ============================================
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ============================================
    # API endpoints (дві версії одночасно)
    # ============================================
    path('api/', include((api_patterns, 'api'), namespace='api')),
    path('api/v1/', include((api_patterns, 'api_v1'), namespace='api_v1')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
