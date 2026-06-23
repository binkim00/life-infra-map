from django.contrib import admin
from .models import Place, Tag, PlaceTag, UserSearchLog


admin.site.register(Place)
admin.site.register(Tag)
admin.site.register(PlaceTag)


@admin.register(UserSearchLog)
class UserSearchLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "query",
        "scenario",
        "category_hint",
        "result_count",
        "created_at",
    )
    list_filter = ("scenario", "category_hint", "created_at")
    search_fields = ("query", "location_hint", "target_query")
