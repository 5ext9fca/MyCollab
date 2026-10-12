from rest_framework import serializers

from accounts.serializers import UserBriefSerializer

from .models import Comment, Mission, MissionEvent, Tag
from .services import allowed_actions


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]


class MissionListSerializer(serializers.ModelSerializer):
    creator = UserBriefSerializer(read_only=True)
    assignee = UserBriefSerializer(read_only=True)
    parent = serializers.UUIDField(source="parent_id", read_only=True, allow_null=True)
    tags = TagSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        fields = [
            "id",
            "title",
            "status",
            "creator",
            "assignee",
            "parent",
            "tags",
            "version",
            "created_at",
            "updated_at",
            "allowed_actions",
        ]

    def get_allowed_actions(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return allowed_actions(user, obj)


class MissionDetailSerializer(MissionListSerializer):
    children = serializers.SerializerMethodField()

    class Meta(MissionListSerializer.Meta):
        fields = MissionListSerializer.Meta.fields + [
            "content",
            "acceptance_criteria",
            "result",
            "children",
        ]

    def get_children(self, obj):
        children = obj.children.select_related("creator", "assignee").prefetch_related("tags").order_by(
            "created_at"
        )
        return MissionListSerializer(children, many=True, context=self.context).data


class MissionEventSerializer(serializers.ModelSerializer):
    actor = UserBriefSerializer(read_only=True)

    class Meta:
        model = MissionEvent
        fields = ["id", "actor", "action", "payload", "created_at"]


class MissionCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(required=False, allow_blank=True, default="")
    acceptance_criteria = serializers.CharField(required=False, allow_blank=True, default="")
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, default=list
    )
    parent = serializers.UUIDField(required=False, allow_null=True)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("标题不能为空。")
        return value


class MissionUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    title = serializers.CharField(max_length=200, required=False)
    content = serializers.CharField(required=False, allow_blank=True)
    acceptance_criteria = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=50), required=False)
    parent = serializers.UUIDField(required=False, allow_null=True)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("标题不能为空。")
        return value


class SubmitSerializer(serializers.Serializer):
    result = serializers.CharField()


class ReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class CommentSerializer(serializers.ModelSerializer):
    """Read model for a mission comment (Markdown content, like Mission.content)."""

    author = UserBriefSerializer(read_only=True)
    mission = serializers.UUIDField(source="mission_id", read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "mission",
            "author",
            "content",
            "created_at",
            "updated_at",
            "can_edit",
        ]

    def get_can_edit(self, obj: Comment) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and obj.author_id == user.pk)


class CommentCreateSerializer(serializers.Serializer):
    # Mirrors Mission.content: Markdown text, blank allowed.
    content = serializers.CharField(required=False, allow_blank=True, default="")


class CommentUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(required=True, allow_blank=True)
