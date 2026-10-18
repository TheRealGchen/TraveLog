from typing import Any

from ..models import SCHEMA_VERSION, ApiModel


def to_document(model: ApiModel) -> dict[str, Any]:
    doc = model.model_dump(mode="python")
    doc["_id"] = doc.pop("id")
    return doc


def from_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Map a stored document to model input, upgrading old schema versions lazily."""
    data = dict(doc)
    data["id"] = data.pop("_id")
    version = data.get("schemaVersion", 1)
    if version > SCHEMA_VERSION:
        raise ValueError(f"document {data['id']} has unknown schemaVersion {version}")
    # Future migrations go here, e.g. `if version < 2: data = _v1_to_v2(data)`.
    data["schemaVersion"] = SCHEMA_VERSION
    return data


def version_filter(if_match: list[Any] | None) -> dict[str, Any]:
    """Extra filter that makes a write apply only if the document's version matches If-Match."""
    return {} if if_match is None else {"updatedAt": {"$in": if_match}}
