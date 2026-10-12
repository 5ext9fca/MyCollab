import uuid

from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from . import services
from .exceptions import ValidationFailure
from .models import Comment, Mission, MissionStatus, Tag
from .permissions import IsTeamMember
from .serializers import (
    CancelSerializer,
    CommentCreateSerializer,
    CommentSerializer,
    CommentUpdateSerializer,
    MissionCreateSerializer,
    MissionDetailSerializer,
    MissionEventSerializer,
    MissionListSerializer,
    MissionUpdateSerializer,
    ReviewSerializer,
    SubmitSerializer,
    TagSerializer,
)

ORDERING_FIELDS = {"created_at", "updated_at", "title", "status"}


def _parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationFailure(
            f"无效的 {field} 参数。", field_errors={field: ["不是合法的 UUID。"]}
        )


class MissionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsTeamMember]
    # PUT and DELETE are intentionally absent: transitions go through actions.
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Mission.objects.select_related("creator", "assignee", "parent").prefetch_related("tags")
        params = self.request.query_params

        status = params.get("status")
        if status:
            if status not in MissionStatus.values:
                raise ValidationFailure(
                    "无效的 status 参数。", field_errors={"status": ["未知状态。"]}
                )
            qs = qs.filter(status=status)

        # Multi-tag filter: repeat the parameter (?tag=a&tag=b) or use commas
        # (?tag=a,b). Multiple tags are ANDed, so a mission must carry every
        # requested tag. Each name gets its own filter() to force a separate
        # join on the M2M table; distinct() below removes the duplicated rows.
        tag_names = [
            name.strip()
            for raw in params.getlist("tag")
            for name in raw.split(",")
        ]
        for name in dict.fromkeys(name for name in tag_names if name):
            qs = qs.filter(tags__name=name)

        creator = params.get("creator")
        if creator == "me":
            qs = qs.filter(creator=self.request.user)
        elif creator:
            qs = qs.filter(creator_id=_parse_uuid(creator, "creator"))

        assignee = params.get("assignee")
        if assignee == "me":
            qs = qs.filter(assignee=self.request.user)
        elif assignee == "none":
            qs = qs.filter(assignee__isnull=True)
        elif assignee:
            qs = qs.filter(assignee_id=_parse_uuid(assignee, "assignee"))

        parent = params.get("parent")
        if parent == "root":
            qs = qs.filter(parent__isnull=True)
        elif parent:
            qs = qs.filter(parent_id=_parse_uuid(parent, "parent"))

        search = params.get("search")
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))

        ordering = params.get("ordering")
        if ordering and ordering.lstrip("-") in ORDERING_FIELDS:
            qs = qs.order_by(ordering)

        return qs.distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return MissionCreateSerializer
        if self.action == "partial_update":
            return MissionUpdateSerializer
        if self.action in ("list", "children"):
            return MissionListSerializer
        return MissionDetailSerializer

    # -- CRUD ------------------------------------------------------------- #
    def create(self, request, *args, **kwargs):
        serializer = MissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mission = services.create_mission(
            actor=request.user,
            title=data["title"],
            content=data.get("content", ""),
            acceptance_criteria=data.get("acceptance_criteria", ""),
            tags=data.get("tags"),
            parent_id=data.get("parent"),
        )
        output = MissionDetailSerializer(mission, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        mission = self.get_object()
        serializer = MissionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        version = data.pop("version")
        mission = services.update_mission(
            actor=request.user, mission_id=mission.id, version=version, changes=data
        )
        output = MissionDetailSerializer(mission, context=self.get_serializer_context())
        return Response(output.data)

    # -- Actions ---------------------------------------------------------- #
    def _detail_response(self, mission):
        return Response(
            MissionDetailSerializer(mission, context=self.get_serializer_context()).data
        )

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        mission = self.get_object()
        mission = services.claim_mission(actor=request.user, mission_id=mission.id)
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        mission = self.get_object()
        mission = services.release_mission(actor=request.user, mission_id=mission.id)
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        mission = self.get_object()
        serializer = SubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mission = services.submit_mission(
            actor=request.user, mission_id=mission.id, result=serializer.validated_data["result"]
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        mission = self.get_object()
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mission = services.review_mission(
            actor=request.user,
            mission_id=mission.id,
            approve=serializer.validated_data["approve"],
            comment=serializer.validated_data.get("comment", ""),
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        mission = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mission = services.cancel_mission(
            actor=request.user,
            mission_id=mission.id,
            reason=serializer.validated_data.get("reason", ""),
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        mission = self.get_object()
        qs = mission.events.select_related("actor").order_by("-created_at")
        page = self.paginate_queryset(qs)
        serializer = MissionEventSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        mission = self.get_object()
        qs = (
            mission.children.select_related("creator", "assignee")
            .prefetch_related("tags")
            .order_by("created_at")
        )
        page = self.paginate_queryset(qs)
        serializer = MissionListSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        mission = self.get_object()
        if request.method == "POST":
            serializer = CommentCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            comment = services.create_comment(
                actor=request.user,
                mission_id=mission.id,
                content=serializer.validated_data["content"],
            )
            output = CommentSerializer(comment, context=self.get_serializer_context())
            return Response(output.data, status=status.HTTP_201_CREATED)

        qs = mission.comments.select_related("author").order_by("-created_at")
        page = self.paginate_queryset(qs)
        serializer = CommentSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)


class CommentViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Edit or delete a single comment; the service layer enforces authorship."""

    permission_classes = [IsTeamMember]
    serializer_class = CommentSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Comment.objects.select_related("author", "mission")

    def partial_update(self, request, *args, **kwargs):
        comment = self.get_object()
        serializer = CommentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = services.update_comment(
            actor=request.user,
            comment_id=comment.id,
            content=serializer.validated_data["content"],
        )
        output = CommentSerializer(comment, context=self.get_serializer_context())
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        comment = self.get_object()
        services.delete_comment(actor=request.user, comment_id=comment.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TagListView(ListAPIView):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsTeamMember]
    pagination_class = None
