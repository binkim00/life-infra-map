from django.contrib import admin
from .models import (
    DataSourceSyncRun,
    Place,
    PlaceCoverage,
    PlaceReport,
    PlaceReportImage,
    PlaceTag,
    PlaceTagEvidence,
    SourcePlaceRecord,
    Tag,
    UserPreference,
    UserSearchLog,
)


admin.site.register(Place)
admin.site.register(Tag)
admin.site.register(PlaceTag)


@admin.register(DataSourceSyncRun)
class DataSourceSyncRunAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "dataset", "sync_type", "status", "started_at", "completed_at")
    list_filter = ("source", "dataset", "sync_type", "status")
    search_fields = ("source", "dataset", "source_uri", "source_checksum")
    readonly_fields = ("started_at", "completed_at")


@admin.register(SourcePlaceRecord)
class SourcePlaceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "business_status",
        "sido_name",
        "sigungu_name",
        "normalized_place",
        "last_seen_at",
    )
    list_filter = ("source", "dataset", "category", "is_active", "sido_name")
    search_fields = ("name", "address", "road_address", "source_record_id")
    readonly_fields = ("created_at", "updated_at", "last_seen_at")


@admin.register(PlaceTagEvidence)
class PlaceTagEvidenceAdmin(admin.ModelAdmin):
    list_display = ("id", "place", "tag", "polarity", "source", "confidence", "observed_at")
    list_filter = ("source", "polarity", "confidence")
    search_fields = ("place__name", "tag__name", "evidence", "source_reference")


@admin.register(PlaceCoverage)
class PlaceCoverageAdmin(admin.ModelAdmin):
    list_display = (
        "administrative_code",
        "sido_name",
        "sigungu_name",
        "category",
        "source_record_count",
        "normalized_place_count",
        "tagged_place_count",
        "evidence_place_count",
        "coverage_score",
    )
    list_filter = ("source", "category", "sido_name")
    search_fields = ("administrative_code", "sido_name", "sigungu_name")


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
