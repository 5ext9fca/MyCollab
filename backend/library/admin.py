from django.contrib import admin

from .models import LibraryFile


@admin.register(LibraryFile)
class LibraryFileAdmin(admin.ModelAdmin):
    """Inspection only: uploads and deletes go through ``library.services``."""

    list_display = ["original_name", "owner", "content_type", "size", "created_at"]
    list_filter = ["content_type", "created_at"]
    search_fields = ["original_name", "owner__username"]
    readonly_fields = [
        "id",
        "owner",
        "file",
        "original_name",
        "content_type",
        "size",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
