from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response

from users.models import NotificationSourceEnum

from .models import Incident, IncidentMessage, IncidentStatusEnum
from .serializers import (
    AudioMessageSerializer,
    DutyPointSerializer,
    DutySerializer,
    IncidentMessageSerializer,
    IncidentSerializer,
    PhotoMessageSerializer,
    TextMessageSerializer,
    VideoMessageSerializer,
)
from .services.access import has_dispatch_admin_rights
from .services.duties import get_duties_by_date, get_current_duties, get_all_duties, get_duty_by_id, \
    get_related_duty_points, get_duty_point_by_duty_role
from .services.incidents import escalate_incident, user_incidents
from .services.messages import create_incident_acceptance_message, create_close_escalation_message, \
    create_force_close_escalation_message, create_reopen_escalation_message
from .services.notification import notify_point_admins, create_and_notify
from .utils import now


class ListRetrieveOnlyPermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        if hasattr(view, 'action'):
            return view.action in ['list', 'retrieve']

        return False


class DutyPointViewSet(viewsets.ModelViewSet):
    serializer_class = DutyPointSerializer
    permission_classes = [ListRetrieveOnlyPermission, IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return get_related_duty_points(user)


class IncidentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        incidents = Incident.objects.all()
        serializer = IncidentSerializer(incidents, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        incident = Incident.objects.get(pk=pk)
        serializer = IncidentSerializer(incident)
        return Response(serializer.data)

    def create(self, request):
        serializer = IncidentSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            incident = serializer.save()
            escalate_incident(incident, request.user)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=["get"])
    def available_actions(self, request, pk=None):
        incident = Incident.objects.get(pk=pk)

        is_admin = has_dispatch_admin_rights(request.user, incident.point)

        response = []

        if (incident.responsible_user == request.user and incident.status != IncidentStatusEnum.WAITING_TO_BE_ACCEPTED) or is_admin:
            if incident.status != IncidentStatusEnum.OPENED.value:
                response.append(IncidentStatusEnum.OPENED.value)
            if incident.status != IncidentStatusEnum.CLOSED.value:
                response.append(IncidentStatusEnum.CLOSED.value)

            if incident.level < 4:
                response.append("escalate")

            if is_admin:
                if incident.status != IncidentStatusEnum.FORCE_CLOSED.value:
                    response.append(IncidentStatusEnum.FORCE_CLOSED.value)

        return Response(response)

    @action(detail=True, methods=["post"])
    def change_status(self, request, pk=None):
        incident = Incident.objects.get(pk=pk)

        is_admin = has_dispatch_admin_rights(request.user, incident.point)

        if incident.responsible_user != request.user and not is_admin:
            return Response({"error": "Вы не являетесь ответственным за этот инцидент"}, status=403)

        new_status = request.data.get("status")

        if new_status not in [e.value for e in IncidentStatusEnum]:
            return Response({"error": "Некорректный статус"}, status=400)

        if new_status in ["force_closed"] and not is_admin:
            return Response({"error": "Принудительно закрыть может только dispatch_admin_manager"}, status=400)

        incident.status = new_status
        incident.save()

        if new_status == "closed":
            create_close_escalation_message(incident, request.user)
        elif new_status == "force_closed":
            create_force_close_escalation_message(incident, request.user)
        elif new_status == "opened":
            if incident.status in [IncidentStatusEnum.FORCE_CLOSED.value, IncidentStatusEnum.CLOSED.value]:
                create_reopen_escalation_message(incident, request.user)
            elif incident.status in [IncidentStatusEnum.WAITING_TO_BE_ACCEPTED.value]:
                if incident.responsible_user == request.user:
                    create_incident_acceptance_message(incident, request.user)
                else:
                    return Response({"error": "Принять инцидент может только ответственный"}, status=403)

        serializer = IncidentSerializer(incident)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        incident = Incident.objects.get(pk=pk)

        is_admin = has_dispatch_admin_rights(request.user, incident.point)

        if incident.responsible_user != request.user and not is_admin:
            return Response({"error": "Вы не являетесь ответственным за этот инцидент"}, status=403)

        escalate_incident(incident, request.user)

        serializer = IncidentSerializer(incident)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def my_incidents(self, request):
        incidents = user_incidents(request.user)

        serializer = IncidentSerializer(incidents, many=True)
        return Response(serializer.data)


class DutyViewSet(viewsets.ReadOnlyModelViewSet):  # ReadOnly since no update/create
    permission_classes = [IsAuthenticated]
    serializer_class = DutySerializer
    queryset = get_all_duties()
    filterset_fields = ['date', 'role', 'is_opened']

    def get_queryset(self):
        queryset = super().get_queryset()
        date_str = self.request.query_params.get('date')

        if date_str:
            date = parse_date(date_str)
            if date:
                queryset = get_duties_by_date(date)

        return queryset

    @action(detail=False, methods=['get'])
    def my_duties(self, request):
        serializer = DutySerializer(get_current_duties(now(), request.user, start_offset=30), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def open(self, request, pk=None):
        duty = get_duty_by_id(pk)

        if duty.user != request.user:
            return Response({"error": "Открыть дежурство может только сам дежурный"}, status=403)

        duty.is_opened = True
        duty.save()

        serializer = DutySerializer(duty)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def transfer_duty(self, request, pk=None):
        duty = get_duty_by_id(pk)

        if duty.user != request.user:
            return Response({"error": "Передать дежурство может только сам дежурный"}, status=403)

        new_user_id = request.data.get("user_id")
        transfer_reason = request.data.get('user_reason') or "Причина не указана"

        if new_user_id == 0:
            for point in get_duty_point_by_duty_role(duty.role):
                notify_point_admins(
                    point,
                    f"{duty.user.display_name} не может выйти на дежурство",
                    f"Необходимо найти замену для {duty.role.name} на системе дежурств {point.name}. Причина пользователя: {transfer_reason}",
                    NotificationSourceEnum.DISPATCH.value,
                )
                return Response(status=204)

        if not get_user_model().objects.filter(pk=new_user_id).exists():
            return Response({"error": "Поле user_id в теле запроса некорректное"}, status=403)

        previous_user = duty.user
        duty.user = get_user_model().objects.get(pk=new_user_id)
        duty.notification_duty_is_coming = None
        duty.notification_need_to_open = None
        duty.save()

        serializer = DutySerializer(duty)
        create_and_notify(
            duty.user,
            "Вам передано дежурство",
            f"{previous_user.user} передал вам дежурство, по причине: {transfer_reason}",
            NotificationSourceEnum.DISPATCH.value,
        )

        for point in get_duty_point_by_duty_role(duty.role):
            notify_point_admins(
                point,
                f"{request.user.display_name} не может выйти на дежурство",
                f"{request.user.display_name} передал {duty.user.display_name} дежурство {duty.role.name} на системе дежурств {point.name}. Причина пользователя: {request.data.get('user_reason')}",
                NotificationSourceEnum.DISPATCH.value,
            )

        return Response(serializer.data)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 1000


class IncidentMessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    serializer_class = IncidentMessageSerializer

    def get_queryset(self):
        return IncidentMessage.objects.filter(incident_id=self.kwargs['incident_pk']).order_by('-created_at')

    def create(self, request, **kwargs):
        user = request.user if request.user.is_authenticated else None
        message_type = request.data.get("message_type")

        msg = IncidentMessage.objects.create(
            user=user,
            message_type=message_type,
            incident_id=self.kwargs['incident_pk'],
            content_type=None,
            object_id=None
        )

        serializer_class = {
            IncidentMessage.TEXT: TextMessageSerializer,
            IncidentMessage.PHOTO: PhotoMessageSerializer,
            IncidentMessage.VIDEO: VideoMessageSerializer,
            IncidentMessage.AUDIO: AudioMessageSerializer,
        }.get(message_type)

        if not serializer_class:
            return Response({"error": "Invalid message type"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = serializer_class(data=request.data)
        if serializer.is_valid():
            content_obj = serializer.save(message=msg)
            msg.content_type = ContentType.objects.get_for_model(content_obj)
            msg.object_id = content_obj.id
            msg.save()
            return Response(IncidentMessageSerializer(msg).data, status=status.HTTP_201_CREATED)

        msg.delete()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
