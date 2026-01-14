from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils import timezone

from users.models import PasswordResetToken
from users.services.sms import send_sms
from users.serializers_password_reset import (
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)


class PasswordResetRequestView(APIView):
    """Запрос на восстановление пароля через SMS"""
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        phone = serializer.validated_data['phone']
        User = get_user_model()
        
        # Ищем пользователя по телефону
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            # Не раскрываем информацию о том, существует ли пользователь
            return Response({
                'message': 'Если пользователь с таким номером телефона существует, на него будет отправлен код подтверждения.'
            }, status=status.HTTP_200_OK)
        
        # Создаем токен и код
        token_obj = PasswordResetToken.create_token(user, phone)
        
        # Отправляем SMS с кодом
        message = f"Код для восстановления пароля: {token_obj.code}. Действителен 15 минут."
        sms_sent = send_sms(phone, message)
        
        if not sms_sent:
            token_obj.delete()
            return Response({
                'error': 'Не удалось отправить SMS. Попробуйте позже.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'message': 'Код подтверждения отправлен на указанный номер телефона.',
            'token': token_obj.token  # Возвращаем токен для следующего шага
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """Подтверждение восстановления пароля с кодом из SMS"""
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        token = serializer.validated_data['token']
        code = serializer.validated_data['code']
        new_password = serializer.validated_data['new_password']
        
        # Находим токен
        try:
            token_obj = PasswordResetToken.objects.get(token=token, is_used=False)
        except PasswordResetToken.DoesNotExist:
            return Response({
                'error': 'Неверный или истекший токен.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Проверяем валидность токена
        if not token_obj.is_valid():
            return Response({
                'error': 'Токен истек. Запросите новый код.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Проверяем код
        if token_obj.code != code:
            return Response({
                'error': 'Неверный код подтверждения.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Устанавливаем новый пароль
        user = token_obj.user
        user.set_password(new_password)
        user.must_change_password = False
        user.save()
        
        # Помечаем токен как использованный
        token_obj.mark_as_used()
        
        return Response({
            'message': 'Пароль успешно изменен.'
        }, status=status.HTTP_200_OK)

