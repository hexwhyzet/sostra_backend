from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password


class PasswordResetRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Номер телефона в формате +7XXXXXXXXXX"
    )
    
    def validate_phone(self, value):
        # Базовая валидация номера телефона
        if not value.startswith('+'):
            raise serializers.ValidationError("Номер телефона должен начинаться с +")
        if len(value) < 10:
            raise serializers.ValidationError("Номер телефона слишком короткий")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    code = serializers.CharField(max_length=6, min_length=6, required=True)
    new_password = serializers.CharField(required=True, write_only=True)
    
    def validate_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Код должен содержать только цифры")
        return value
    
    def validate_new_password(self, value):
        validate_password(value)
        return value


