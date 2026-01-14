import enum

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from dispatch.services.access import has_access_to_dispatch
from myapp.custom_groups import QRGuard, CanteenManager, CanteenEmployee, DispatchAdminManager
from myapp.models import Device
from myapp.serializers import SuccessJsonResponse


class SostraApp(str, enum.Enum):
    canteen = 'canteen'
    canteen_manager = 'canteen_manager'
    qr_patrol = 'qr_patrol'
    dispatch = 'dispatch'


class UserInfo(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        extra = {}
        available_apps = []
        for group in user.groups.all():
            if group.name == QRGuard.name and user.guard_profile.exists():
                extra['guard_id'] = user.guard_profile.first().code
                available_apps.append(SostraApp.qr_patrol.value)
            elif group.name == CanteenManager.name:
                available_apps.append(SostraApp.canteen_manager.value)
            elif group.name == CanteenEmployee.name:
                available_apps.append(SostraApp.canteen.value)
            elif group.name == DispatchAdminManager.name:
                available_apps.append(SostraApp.dispatch.value)

        if has_access_to_dispatch(user):
            available_apps.append(SostraApp.dispatch.value)

        content = {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'display_name': user.display_name,
            'groups': [group.name for group in user.groups.all()], # legacy
            'available_apps': available_apps,
            'extra': extra,
            'must_change_password': user.must_change_password,
        }

        return SuccessJsonResponse(data=content)


class RegisterNotificationToken(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        notification_token = request.data.get('notification_token')

        if not notification_token:
            return Response({'error': 'Notification token is required'}, status=400)

        device, created = Device.objects.update_or_create(user=user,
                                                          defaults={'notification_token': notification_token})

        return Response({'message': 'Notification token registered successfully'}, status=201)
