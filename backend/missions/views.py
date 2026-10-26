from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from . import services
from .exceptions import ValidationFailure
from .filters import apply_mission_filters
from .models import (
    Comment,
    Milestone,
    MilestoneStatus,
    Mission,
    MissionDependency,
    MissionPriority,
    MissionType,
    Tag,
)
from .permissions import IsTeamMember
from .serializers import (
    CancelSerializer,
    ClaimSerializer,
    CommentCreateSerializer,
    CommentSerializer,
    CommentUpdateSerializer,
    DependencyCreateSerializer,
    DependencyRefSerializer,
    MilestoneCreateSerializer,
    MilestoneSerializer,
    MilestoneTransitionSerializer,
    MilestoneUpdateSerializer,
    MissionCreateSerializer,
    MissionDetailSerializer,
    MissionEventSerializer,
    MissionListSerializer,
    MissionRefSerializer,
    MissionSubmissionSerializer,
    MissionUpdateSerializer,
    ReopenSerializer,
    ReviewSerializer,
    SubmitSerializer,
    TagSerializer,
    TransferReviewSerializer,
)

def _require_version(value, field: str = "expected_version") -> int:
    if value is None or value == "":
        raise ValidationFailure(f"缺少 {field}。", field_errors={field: ["必填。"]})
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationFailure(f"无效的 {field}。", field_errors={field: ["不是整数。"]})


class MissionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsTeamMember]
    # PUT is intentionally absent: transitions go through actions.
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Mission.objects.select_related(
            "creator", "assignee", "reviewer", "parent", "milestone", "design_element"
        ).prefetch_related("tags", "assets")
        return apply_mission_filters(qs, self.request.query_params, self.request.user)

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
            type=data.get("type", MissionType.TASK),
            priority=data.get("priority", MissionPriority.P2),
            reviewer_id=data.get("reviewer_id"),
            milestone_id=data.get("milestone_id"),
            design_element_id=data.get("design_element_id"),
            asset_ids=data.get("asset_ids"),
            planned_start_date=data.get("planned_start_date"),
            planned_end_date=data.get("planned_end_date"),
        )
        output = MissionDetailSerializer(mission, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        mission = self.get_object()
        serializer = MissionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        mission = services.update_mission(
            actor=request.user,
            mission_id=mission.id,
            expected_version=expected_version,
            changes=data,
        )
        output = MissionDetailSerializer(mission, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        result = services.bulk_update_missions(actor=request.user, payload=request.data)
        for item in result['results']:
            if item['success']:
                item['mission'] = MissionListSerializer(item['mission'], context=self.get_serializer_context()).data
        return Response(result)

    # -- Actions ---------------------------------------------------------- #
    def _detail_response(self, mission):
        return Response(
            MissionDetailSerializer(mission, context=self.get_serializer_context()).data
        )

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        mission = self.get_object()
        serializer = ClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mission = services.claim_mission(
            actor=request.user,
            mission_id=mission.id,
            expected_version=serializer.validated_data["expected_version"],
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        mission = self.get_object()
        serializer = ClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mission = services.release_mission(
            actor=request.user,
            mission_id=mission.id,
            expected_version=serializer.validated_data["expected_version"],
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        mission = self.get_object()
        serializer = SubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mission = services.submit_mission(
            actor=request.user,
            mission_id=mission.id,
            description=data.get("description", ""),
            verification_description=data.get("verification_description", ""),
            source_references=data.get("source_references"),
            build_references=data.get("build_references"),
            execution_candidate_ids=data.get("execution_candidate_ids"),
            code_execution_ids=data.get("code_execution_ids"),
            expected_version=data["expected_version"],
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        mission = self.get_object()
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mission = services.review_mission(
            actor=request.user,
            mission_id=mission.id,
            submission_id=data["submission_id"],
            decision=data["decision"],
            comment=data.get("comment", ""),
            verified_build_reference_id=data.get("verified_build_reference_id"),
            expected_version=data["expected_version"],
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"], url_path="transfer-review")
    def transfer_review(self, request, pk=None):
        mission = self.get_object()
        serializer = TransferReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mission = services.transfer_review(
            actor=request.user,
            mission_id=mission.id,
            new_reviewer_id=data["new_reviewer_id"],
            reason=data["reason"],
            expected_version=data["expected_version"],
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        mission = self.get_object()
        serializer = ReopenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mission = services.reopen_mission(
            actor=request.user,
            mission_id=mission.id,
            reason=data["reason"],
            expected_version=data["expected_version"],
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        mission = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mission = services.cancel_mission(
            actor=request.user,
            mission_id=mission.id,
            reason=data.get("reason", ""),
            expected_version=data["expected_version"],
        )
        return self._detail_response(mission)

    @action(detail=True, methods=["get", "post"])
    def dependencies(self, request, pk=None):
        mission = self.get_object()
        if request.method == "POST":
            serializer = DependencyCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            services.add_dependency(
                actor=request.user,
                mission_id=mission.id,
                prerequisite_id=data["prerequisite_id"],
                expected_version=data["expected_version"],
            )
            mission = Mission.objects.select_related(
                "creator", "assignee", "reviewer", "parent", "milestone", "design_element"
            ).get(pk=mission.id)
            return self._detail_response(mission)

        prerequisites = (
            MissionDependency.objects.filter(mission=mission)
            .select_related("prerequisite")
            .order_by("created_at")
        )
        dependents = Mission.objects.filter(dependencies__prerequisite_id=mission.id).order_by(
            "created_at"
        )
        return Response(
            {
                "prerequisites": DependencyRefSerializer(prerequisites, many=True).data,
                "dependents": MissionRefSerializer(dependents, many=True).data,
                "has_unresolved_prerequisites": services.derived_state(mission)[
                    "has_unresolved_prerequisites"
                ],
            }
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"dependencies/(?P<dependency_id>[^/.]+)",
    )
    def remove_dependency(self, request, pk=None, dependency_id=None):
        mission = self.get_object()
        expected_version = _require_version(request.query_params.get("expected_version"))
        services.remove_dependency(
            actor=request.user,
            mission_id=mission.id,
            dependency_id=dependency_id,
            expected_version=expected_version,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def submissions(self, request, pk=None):
        mission = self.get_object()
        qs = (
            mission.submissions.select_related(
                "submitted_by", "reviewer_snapshot", "reviewed_by"
            )
            .prefetch_related("source_references", "build_references")
            .order_by("-submitted_at")
        )
        page = self.paginate_queryset(qs)
        serializer = MissionSubmissionSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

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
            mission.children.select_related("creator", "assignee", "reviewer", "milestone")
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


class MilestoneViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsTeamMember]
    serializer_class = MilestoneSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Milestone.objects.select_related("created_by")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in MilestoneStatus.values:
                raise ValidationFailure(
                    "无效的 status 参数。", field_errors={"status": ["未知状态。"]}
                )
            qs = qs.filter(status=status_filter)
        ordering = self.request.query_params.get("ordering", "-created_at")
        if ordering not in ("created_at", "-created_at", "due_date", "name"):
            raise ValidationFailure("无效的里程碑排序。")
        return qs.order_by(ordering, "id")

    def get_serializer_class(self):
        if self.action == "create":
            return MilestoneCreateSerializer
        if self.action == "partial_update":
            return MilestoneUpdateSerializer
        if self.action == "transition":
            return MilestoneTransitionSerializer
        return MilestoneSerializer

    def create(self, request, *args, **kwargs):
        serializer = MilestoneCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        milestone = services.create_milestone(
            actor=request.user,
            name=data["name"],
            description=data.get("description", ""),
            due_date=data.get("due_date"),
        )
        output = MilestoneSerializer(milestone, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        milestone = self.get_object()
        serializer = MilestoneUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        milestone = services.update_milestone(
            actor=request.user,
            milestone_id=milestone.id,
            expected_version=expected_version,
            changes=data,
        )
        output = MilestoneSerializer(milestone, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        milestone = self.get_object()
        serializer = MilestoneTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        milestone = services.transition_milestone(
            actor=request.user,
            milestone_id=milestone.id,
            status=data["status"],
            reason=data.get("reason", ""),
            expected_version=data["expected_version"],
        )
        output = MilestoneSerializer(milestone, context=self.get_serializer_context())
        return Response(output.data)


class TagListView(ListAPIView):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsTeamMember]
    pagination_class = None


class DesignElementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsTeamMember]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        from django.db.models import Q
        from .models import DesignElement
        from .filters import parse_uuid
        qs = DesignElement.objects.select_related("created_by", "parent").prefetch_related("assets", "referencing_designs", "prerequisites", "dependents")
        if self.action != "list":
            return qs
        params = self.request.query_params
        archived = params.get("archived", "false")
        if archived not in {"true", "false", "all"}:
            raise ValidationFailure("无效的归档筛选。")
        if archived != "all":
            qs = qs.filter(archived=archived == "true")
        if params.get("q"):
            qs = qs.filter(Q(title__icontains=params["q"]) | Q(content__icontains=params["q"]))
        if params.get("kind"):
            if params["kind"] not in DesignElement.Kind.values:
                raise ValidationFailure("无效的条目类型。")
            qs = qs.filter(kind=params["kind"])
        if params.get("parent"):
            qs = qs.filter(parent_id=None if params["parent"] == "root" else parse_uuid(params["parent"], "parent"))
        return qs

    def get_serializer_class(self):
        from .serializers import DesignElementSerializer
        return DesignElementSerializer

    def create(self, request):
        from .serializers import DesignCreateSerializer
        data = DesignCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        element = services.create_design_element(actor=request.user, **data.validated_data)
        return Response(self.get_serializer(element).data, status=201)

    def partial_update(self, request, pk=None):
        from .serializers import DesignUpdateSerializer
        element = self.get_object()
        data = DesignUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        changes = dict(data.validated_data)
        element = services.update_design_element(actor=request.user, element_id=element.pk,
            expected_version=changes.pop("expected_version"), changes=changes)
        return Response(self.get_serializer(element).data)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        from .serializers import DesignElementEventSerializer
        rows = self.paginate_queryset(self.get_object().events.select_related("actor"))
        return self.get_paginated_response(DesignElementEventSerializer(rows, many=True).data)


    @action(detail=True, methods=["post"])
    def instantiate(self, request, pk=None):
        from .serializers import InstantiateSerializer
        element = self.get_object()
        data = InstantiateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        batch = services.instantiate_production(actor=request.user, element_id=element.pk, **data.validated_data)
        element.refresh_from_db()
        return Response({"batch_id": str(batch.pk), "asset_version": element.version,
            "template_version": batch.template_version,
            "items": [{"step_key": item.step_key, "mission_id": str(item.mission_id)} for item in batch.items.all()]}, status=201)

    @action(detail=True, methods=["get"])
    def production(self, request, pk=None):
        from .models import ProductionBatch
        element = self.get_object()
        batch = ProductionBatch.objects.filter(asset=element).select_related("created_by").first()
        if batch is None:
            return Response({"batch": None, "items": []})
        items = list(batch.items.select_related("mission__creator", "mission__assignee", "mission__reviewer", "mission__milestone", "mission__design_element").prefetch_related("mission__assets", "mission__tags", "mission__dependencies__prerequisite"))
        derived = services.derived_state_bulk(item.mission for item in items)
        by_key = {}
        for item in items:
            item.mission._derived_cache = derived[item.mission_id]
            summary = dict(MissionListSerializer(item.mission, context=self.get_serializer_context()).data)
            summary["prerequisites"] = DependencyRefSerializer(item.mission.dependencies.all(), many=True).data
            by_key[item.step_key] = {"step_key": item.step_key, "mission": summary}
        return Response({"batch": {"id": str(batch.pk), "template_id": str(batch.template_id),
            "template_version": batch.template_version, "template_snapshot": batch.template_snapshot,
            "created_at": batch.created_at},
            "items": [by_key[step["key"]] for step in batch.template_snapshot["steps"] if step["key"] in by_key]})


class ProductionTemplateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsTeamMember]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        from django.db.models import Q
        from .models import ProductionTemplate
        qs = ProductionTemplate.objects.select_related("created_by")
        if self.action == "list":
            archived = self.request.query_params.get("archived", "false")
            if archived not in {"true", "false", "all"}:
                raise ValidationFailure("无效的归档筛选。")
            if archived != "all":
                qs = qs.filter(archived=archived == "true")
            q = self.request.query_params.get("q")
            if q:
                qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return qs

    def get_serializer_class(self):
        from .serializers import ProductionTemplateSerializer
        return ProductionTemplateSerializer

    def create(self, request):
        from .serializers import ProductionTemplateCreateSerializer
        data = ProductionTemplateCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        template = services.create_production_template(actor=request.user, **data.validated_data)
        return Response(self.get_serializer(template).data, status=201)

    def partial_update(self, request, pk=None):
        from .serializers import ProductionTemplateUpdateSerializer
        template = self.get_object()
        data = ProductionTemplateUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        changes = dict(data.validated_data)
        template = services.update_production_template(actor=request.user, template_id=template.pk,
            expected_version=changes.pop("expected_version"), changes=changes)
        return Response(self.get_serializer(template).data)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        from .serializers import ProductionTemplateEventSerializer
        rows = self.paginate_queryset(self.get_object().events.select_related("actor"))
        return self.get_paginated_response(ProductionTemplateEventSerializer(rows, many=True).data)
