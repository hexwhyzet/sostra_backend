from django.contrib.auth import get_user_model
from rest_framework import serializers

from users.models import display_name, Notification


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        validate_password(value)
        return value


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'first_name', 'last_name', 'display_name']

    def get_display_name(self, obj):
        return display_name(obj)


class NotificationSerializer(serializers.ModelSerializer):
    duty_action_id = serializers.IntegerField(source="duty_action.id", read_only=True)
    duty_id = serializers.IntegerField(source="duty_action.duty.id", read_only=True)
    is_resolved = serializers.IntegerField(
        source="duty_action.is_resolved", read_only=True
    )

    def get_duty_action_reason(self, obj):
        value = getattr(obj.duty_action, "reason", None)
        if not value or len(value) == 0:
            return "не указана"
        return value

    duty_action_reason = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "source",
            "text",
            "created_at",
            "is_seen",
            "duty_id",
            "duty_action_id",
            "is_resolved",
            "duty_action_reason",
        ]
