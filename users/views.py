from django.contrib.auth import update_session_auth_hash, get_user_model
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import Notification
from users.serializers import (
    ChangePasswordSerializer,
    NotificationSerializer,
    UserSerializer,
)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({"old_password": ["Старый пароль неправильный."]}, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(serializer.validated_data['new_password'])
            user.must_change_password = False
            user.save()
            update_session_auth_hash(request, user)  # чтобы не вышло из сессии
            return Response({"detail": "Пароль сменен успешно."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserListAPIView(ListAPIView):
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = get_user_model()._meta.ordering


class UserNotificationsView(ListAPIView):
    def get(self, request, user_id):
        try:
            queryset = Notification.objects.filter(user_id=user_id).order_by(
                "-created_at"
            )

            result = []
            for elem in queryset:
                elem.source = elem.get_source_display()
                result.append(elem)

            serializer = NotificationSerializer(result, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except (Exception,) as e:
            return Response(
                {"error": "Не найдены уведомления для пользователя с таким ID."},
                status=status.HTTP_404_NOT_FOUND,
            )


class ReadUserNotificationView(APIView):
    def post(self, request, user_id, notification_id):
        try:
            notification = Notification.objects.get(id=notification_id, user_id=user_id)

            notification.is_seen = True
            notification.save()

            return Response("success", status=status.HTTP_200_OK)

        except (Exception,) as e:
            return Response(
                {"error": "Не найдено уведомление с таким ID для пользователя."},
                status=status.HTTP_404_NOT_FOUND,
            )
