from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed


User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_active',
            'password',
        )

    def validate_is_active(self, value):
        # якщо is_active не змінюється (тобто те саме значення) — пропускаємо
        if self.instance is not None and self.instance.is_active == value:
            return value

        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Not allowed.")

        if not user.is_admin():
            raise serializers.ValidationError("Only admin can change is_active.")

        return value

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # КРИТИЧНО

        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance

try:
    from .models import UserProfile
    class UserProfileSerializer(serializers.ModelSerializer):
        class Meta:
            model = UserProfile
            fields = ('id', 'user', 'avatar', 'biography', 'phone', 'languages',
            'country',
            'city',)
            read_only_fields = ('user',)
except Exception:

    UserProfileSerializer = None



class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):

    username_field = 'email'

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise AuthenticationFailed('Email and password are required.')


        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise AuthenticationFailed('No active account found with the given credentials.')
        except User.MultipleObjectsReturned:
            raise AuthenticationFailed('Multiple users with this email exist. Contact admin.')


        if not user.check_password(password):
            raise AuthenticationFailed('No active account found with the given credentials.')


        if not user.is_active:
            raise AuthenticationFailed('User account is disabled.')


        data = super().validate({
            'email': user.email, 'password': password
        })

        return data