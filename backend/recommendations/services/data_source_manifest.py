import json
from functools import lru_cache
from pathlib import Path


MANIFEST_DIR = Path(__file__).resolve().parents[1] / "data_sources"


@lru_cache(maxsize=None)
def load_data_source_manifest(source):
    path = MANIFEST_DIR / f"{source}.json"
    if not path.exists():
        raise ValueError(f"Unknown data source manifest: {source}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_dataset_config(source, dataset):
    manifest = load_data_source_manifest(source)
    try:
        return manifest, manifest["datasets"][dataset]
    except KeyError as exc:
        raise ValueError(f"Unknown {source} dataset: {dataset}") from exc
