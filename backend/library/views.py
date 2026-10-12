from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.exceptions import NotFound
from common.permissions import IsTeamMember

from . import services
from .models import LibraryFile
from .serializers import LibraryFileSerializer, LibraryFileUploadSerializer


class LibraryFileViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Per-user file library.

    * ``list`` - the caller's own files (for pickers and management)
    * ``create`` - upload into the caller's library
    * ``retrieve`` - authorized download; any authenticated member may read
    * ``destroy`` - delete; the service layer enforces ownership
    """

    permission_classes = [IsTeamMember]
    serializer_class = LibraryFileSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = LibraryFile.objects.select_related("owner")
        if self.action == "list":
            return qs.filter(owner=self.request.user)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = LibraryFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = services.save_library_file(
            actor=request.user, upload=serializer.validated_data["file"]
        )
        output = LibraryFileSerializer(record, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        return _file_response(self.get_object())

    def destroy(self, request, *args, **kwargs):
        record = self.get_object()
        services.delete_library_file(actor=request.user, file_id=record.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _file_response(record: LibraryFile) -> FileResponse:
    """Stream a stored file with a safe content type and disposition."""
    file_field = record.file
    try:
        file_field.open("rb")
    except FileNotFoundError:
        raise NotFound("文件不存在。")

    response = FileResponse(
        file_field,
        content_type=record.content_type,
        as_attachment=not record.is_image,
        filename=record.original_name,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
