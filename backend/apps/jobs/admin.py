from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "operation", "bucket", "file_key", "progress", "created_at")
    list_filter = ("status", "operation")
    search_fields = ("id", "bucket", "file_key")
    readonly_fields = ("id", "created_at", "updated_at")
    # Never expose the encrypted credential blob in the admin UI.
    exclude = ("encrypted_credentials",)
