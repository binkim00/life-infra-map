from django.contrib import admin
from .models import (
    Place,
    PlaceReport,
    PlaceReportImage,
    PlaceTag,
    Tag,
    UserPreference,
    UserSearchLog,
)


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


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "preference_type",
        "label",
        "score",
        "search_count",
        "last_seen_at",
    )
    list_filter = ("preference_type", "source", "last_seen_at")
    search_fields = ("label", "key", "user__username")


class PlaceReportImageInline(admin.TabularInline):
    model = PlaceReportImage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(PlaceReport)
class PlaceReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "report_type",
        "status",
        "place",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("report_type", "status", "created_at")
    search_fields = (
        "user__username",
        "place__name",
        "suggested_name",
        "suggested_address",
        "description",
    )
    inlines = [PlaceReportImageInline]


@admin.register(PlaceReportImage)
class PlaceReportImageAdmin(admin.ModelAdmin):
    list_display = ("id", "report", "original_name", "created_at")
    search_fields = ("original_name", "report__description")
