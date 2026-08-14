import os
from urllib.parse import unquote

import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from recommendations.management.commands.import_localdata_records import (
    build_source_record,
    save_batch,
)
from recommendations.models import DataSourceSyncRun, SourcePlaceRecord
from recommendations.services.data_source_manifest import get_dataset_config


class Command(BaseCommand):
    help = "Synchronize a LOCALDATA nationwide dataset through data.go.kr OpenAPI."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--page-size", type=int, default=100)
        parser.add_argument("--start-page", type=int, default=1)
        parser.add_argument("--max-pages", type=int)
        parser.add_argument("--timeout", type=int, default=30)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            manifest, dataset_config = get_dataset_config(
                "localdata", options["dataset"]
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        key_name = dataset_config.get(
            "service_key_environment_variable",
            manifest["service_key_environment_variable"],
        )
        service_key = normalize_service_key(os.getenv(key_name, ""))
        if not service_key:
            raise CommandError(
                f"{key_name} is required. Apply for the official data.go.kr API first."
            )

        stats = sync_localdata_api(
            dataset=options["dataset"],
            dataset_config=dataset_config,
            service_key=service_key,
            page_size=max(1, min(options["page_size"], 1000)),
            start_page=max(1, options["start_page"]),
            max_pages=options["max_pages"],
            timeout=max(1, options["timeout"]),
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}LOCALDATA API sync complete: pages={stats['pages']} "
                f"read={stats['read']} valid={stats['valid']} "
                f"created={stats['created']} updated={stats['updated']} "
                f"skipped={stats['skipped']} duplicates={stats['duplicates']}"
            )
        )


def sync_localdata_api(
    *,
    dataset,
    dataset_config,
    service_key,
    page_size=1000,
    start_page=1,
    max_pages=None,
    timeout=30,
    dry_run=False,
    session=None,
):
    client = session or requests.Session()
    stats = {
        "pages": 0,
        "read": 0,
        "valid": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "duplicates": 0,
        "total_count": None,
    }
    stats['exhausted'] = False
    sync_run = None
    if not dry_run:
        sync_run = DataSourceSyncRun.objects.create(
            source="localdata",
            dataset=dataset,
            sync_type="full" if start_page == 1 else "delta",
            source_uri=dataset_config["api_url"],
            cursor={"next_page": start_page},
        )

    try:
        page = start_page
        effective_page_size = None
        while max_pages is None or stats["pages"] < max_pages:
            try:
                response = client.get(
                    dataset_config["api_url"],
                    params={
                        "serviceKey": service_key,
                        "pageNo": page,
                        "numOfRows": page_size,
                        "type": "json",
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                status = getattr(exc.response, "status_code", None)
                detail = f"HTTP {status}" if status else exc.__class__.__name__
                raise CommandError(
                    f"LOCALDATA API request failed ({detail}) for dataset {dataset}."
                ) from None
            items, total_count = parse_api_response(response.json())
            if total_count is not None:
                stats["total_count"] = total_count
            if not items:
                stats['exhausted'] = True
                break
            if effective_page_size is None:
                effective_page_size = len(items)

            batch = []
            for item in items:
                stats["read"] += 1
                record_data = build_source_record(
                    item,
                    source="localdata",
                    dataset=dataset,
                    default_category=dataset_config["category"],
                )
                if record_data is None:
                    stats["skipped"] += 1
                    continue
                stats["valid"] += 1
                if not dry_run:
                    batch.append(SourcePlaceRecord(**record_data))
            if batch:
                save_batch(batch, stats)

            stats["pages"] += 1
            page += 1
            if sync_run is not None:
                sync_run.cursor = {"next_page": page}
                sync_run.stats = stats
                sync_run.save(update_fields=["cursor", "stats"])
            if (
                total_count is not None
                and effective_page_size
                and (start_page - 1) * effective_page_size + stats["read"]
                >= total_count
            ):
                stats['exhausted'] = True
                break

        if sync_run is not None:
            sync_run.status = "succeeded"
            sync_run.stats = stats
            sync_run.completed_at = timezone.now()
            sync_run.save(update_fields=["status", "stats", "completed_at"])
        return stats
    except Exception as exc:
        if sync_run is not None:
            sync_run.status = "failed"
            sync_run.stats = stats
            sync_run.cursor = {"next_page": page}
            sync_run.error_message = str(exc)[:4000]
            sync_run.completed_at = timezone.now()
            sync_run.save(
                update_fields=[
                    "status",
                    "stats",
                    "cursor",
                    "error_message",
                    "completed_at",
                ]
            )
        raise


def normalize_service_key(value):
    """Accept either data.go.kr's encoded or decoded service key."""
    return unquote((value or "").strip())


def parse_api_response(payload):
    response = payload.get("response", payload)
    header = response.get("header", {}) if isinstance(response, dict) else {}
    result_code = str(header.get("resultCode", "00"))
    if result_code not in {"00", "0", "NORMAL_SERVICE"}:
        raise CommandError(
            f"LOCALDATA API error {result_code}: {header.get('resultMsg', '')}"
        )

    body = response.get("body", response) if isinstance(response, dict) else {}
    items_container = body.get("items", []) if isinstance(body, dict) else []
    if isinstance(items_container, dict):
        items = items_container.get("item", [])
    else:
        items = items_container
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []

    total_count = body.get("totalCount") if isinstance(body, dict) else None
    try:
        total_count = int(total_count) if total_count is not None else None
    except (TypeError, ValueError):
        total_count = None
    return items, total_count
