from rest_framework import serializers

from .models import LibraryFile


class LibraryFileSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)

    class Meta:
        model = LibraryFile
        fields = ["id", "original_name", "content_type", "size", "url", "created_at"]


class LibraryFileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
