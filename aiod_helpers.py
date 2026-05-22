"""Helper functions for AIoD SDK, REST, and local upload-history operations."""

import json
import traceback
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiod
import requests

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


APPLICATION_AREAS_URL = "https://api.aiodp.eu/application_areas"
RESEARCH_AREAS_URL = "https://api.aiodp.eu/research_areas"
INDUSTRIAL_SECTORS_URL = "https://api.aiodp.eu/industrial_sectors"
LICENSES_URL = "https://api.aiodp.eu/licenses"
SCIENTIFIC_DOMAINS_URL = "https://api.aiodp.eu/scientific_domains"
COMPUTATIONAL_ASSET_TYPES_URL = "https://api.aiodp.eu/computational_asset_types"


def apply_version(version: Optional[str]) -> Optional[str]:
    """Normalize an optional AIoD API version string for SDK calls."""
    version = (version or "").strip()
    return version or None


def current_user() -> Tuple[bool, str]:
    """Check whether the AIoD SDK can resolve the currently authenticated user."""
    try:
        return True, repr(aiod.get_current_user())
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def safe_json(obj: Any) -> str:
    """Serialize an object as readable JSON, falling back to repr on failure."""
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return repr(obj)


def normalize_items(raw: Any) -> List[Dict[str, Any]]:
    """Convert common SDK response shapes into a list of dictionaries."""
    if raw is None:
        return []

    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    # pandas DataFrame support without importing pandas explicitly
    if hasattr(raw, "to_dict"):
        try:
            records = raw.to_dict(orient="records")
            return [x for x in records if isinstance(x, dict)]
        except Exception:
            pass

    if isinstance(raw, dict):
        for key in ("items", "results", "data", "assets"):
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]
        return [raw]

    return []


def text_of(value: Any) -> str:
    """Flatten nested values into searchable text."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(text_of(v) for v in value)
    if isinstance(value, dict):
        return " ".join(text_of(v) for v in value.values())
    return str(value)


# ---------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------


def project_label(project: Dict[str, Any]) -> str:
    """Return the best human-readable label available for an AIoD project."""
    for key in ("name", "title", "project_full_name", "fullname", "acronym"):
        if project.get(key):
            return str(project[key])
    return project.get("identifier", "<unnamed>")


def project_identifier(project: Dict[str, Any]) -> str:
    """Extract a stable project identifier from known AIoD response fields."""
    for key in ("identifier", "ai_resource_identifier", "agent_identifier", "platform_resource_identifier"):
        if project.get(key):
            return str(project[key])
    return ""


def project_summary(project: Dict[str, Any]) -> Dict[str, str]:
    """Build the compact project row used by the Projects page."""
    return {
        "identifier": project_identifier(project),
        "name": project_label(project),
        "platform": str(project.get("platform") or ""),
        "description": str(project.get("description") or project.get("project_description") or "")[:500],
        "raw": safe_json(project),
    }


def search_projects(query: str, version: Optional[str], limit: int = 50) -> Dict[str, Any]:
    """Try several SDK approaches and return visible diagnostics.

    AIoD SDK methods may behave differently across API versions. This function tries:
    1. projects.search(..., asset_type="projects")
    2. projects.get_list paginated and local filtering
    """
    query = (query or "").strip()
    version = apply_version(version)
    q_lower = query.lower()

    diagnostics: List[str] = []
    raw_blocks: List[Dict[str, Any]] = []
    found: List[Dict[str, Any]] = []
    seen = set()

    def add_items(items: List[Dict[str, Any]], source: str, filter_locally: bool = False) -> None:
        """Add normalized project rows while removing duplicates."""
        for item in items:
            haystack = text_of(item).lower()
            if filter_locally and q_lower and q_lower not in haystack:
                continue

            ident = project_identifier(item) or safe_json(item)[:200]
            if ident in seen:
                continue

            seen.add(ident)
            summary = project_summary(item)
            summary["source"] = source
            found.append(summary)

    # 1) Search endpoint via SDK
    try:
        kwargs = {
            "limit": limit,
            "data_format": "json",
            "asset_type": "projects",
        }
        if version:
            kwargs["version"] = version

        search_raw = aiod.projects.search(query, **kwargs)
        search_items = normalize_items(search_raw)

        raw_blocks.append({
            "method": "projects.search",
            "items_count": len(search_items),
            "raw_preview": safe_json(search_raw)[:4000],
        })

        add_items(search_items, "projects.search", filter_locally=False)
        diagnostics.append(f"projects.search: OK, normalized items: {len(search_items)}")
    except Exception as exc:
        diagnostics.append(f"projects.search: ERROR {type(exc).__name__}: {exc}")
        raw_blocks.append({"method": "projects.search", "error": traceback.format_exc()})

    # 2) List endpoint via SDK, with pagination and local filtering
    offsets = [0, 50, 100, 150, 200]
    total_listed = 0

    for offset in offsets:
        try:
            kwargs = {"offset": offset, "limit": 50, "data_format": "json"}
            if version:
                kwargs["version"] = version

            list_raw = aiod.projects.get_list(**kwargs)
            list_items = normalize_items(list_raw)
            total_listed += len(list_items)

            raw_blocks.append({
                "method": f"projects.get_list offset={offset}",
                "items_count": len(list_items),
                "raw_preview": safe_json(list_raw)[:2500],
            })

            add_items(list_items, f"projects.get_list offset={offset}", filter_locally=True)

            if len(list_items) < 50:
                break
        except Exception as exc:
            diagnostics.append(f"projects.get_list offset={offset}: ERROR {type(exc).__name__}: {exc}")
            raw_blocks.append({"method": f"projects.get_list offset={offset}", "error": traceback.format_exc()})
            break

    diagnostics.append(
        "projects.get_list: total items read: "
        f"{total_listed}; results after local filtering: "
        f"{len([x for x in found if 'get_list' in x.get('source', '')])}"
    )

    return {
        "query": query,
        "version": version or "default SDK version",
        "results": found,
        "diagnostics": diagnostics,
        "raw_blocks": raw_blocks,
    }


# ---------------------------------------------------------------------
# SDK result helpers
# ---------------------------------------------------------------------


def extract_identifier(value: Any) -> str:
    """Try to extract an AIoD identifier from SDK register responses."""
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in ("identifier", "id", "asset_identifier", "aiod_identifier"):
            if value.get(key):
                return str(value[key])

        entry = value.get("aiod_entry")
        if isinstance(entry, dict):
            for key in ("identifier", "id", "asset_identifier"):
                if entry.get(key):
                    return str(entry[key])

    # objects with attributes
    for key in ("identifier", "id", "asset_identifier", "aiod_identifier"):
        if hasattr(value, key):
            attr = getattr(value, key)
            if attr:
                return str(attr)

    return ""


def describe_sdk_result(value: Any) -> Dict[str, Any]:
    """Describe an SDK return value in a UI-friendly diagnostic structure."""
    identifier = extract_identifier(value)

    description: Dict[str, Any] = {
        "python_type": f"{type(value).__module__}.{type(value).__name__}",
        "identifier": identifier,
        "raw_repr": repr(value),
        "raw_json_or_str": safe_json(value),
        "is_none": value is None,
    }

    # The SDK may return a requests.Response instead of raising an exception.
    # In that case we expose the real HTTP status and body.
    if hasattr(value, "status_code"):
        description["http_status_code"] = getattr(value, "status_code", None)
        description["http_ok"] = getattr(value, "ok", None)
        description["http_text"] = getattr(value, "text", "")

        try:
            description["http_json"] = value.json()
        except Exception as exc:
            description["http_json_error"] = f"{type(exc).__name__}: {exc}"

    return description


# ---------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------


def split_lines(text: str) -> List[str]:
    """Split a multi-line form value into non-empty stripped strings."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def form_list_values(form: Any, field_name: str) -> List[str]:
    """Read repeated form values or newline text for a multi-value metadata field."""
    if hasattr(form, "getlist"):
        values = form.getlist(field_name)
        if len(values) != 1:
            return [str(value).strip() for value in values if str(value).strip()]

        return split_lines(str(values[0]))

    value = form.get(field_name) if hasattr(form, "get") else None

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    return split_lines(str(value or ""))


def form_repeated_values(form: Any, field_name: str) -> List[str]:
    """Read repeated form values while preserving empty positions."""
    if hasattr(form, "getlist"):
        return [str(value).strip() for value in form.getlist(field_name)]

    value = form.get(field_name) if hasattr(form, "get") else None

    if isinstance(value, list):
        return [str(item).strip() for item in value]

    return [str(value).strip()] if value is not None else []


def parse_optional_int(value: str, field_name: str) -> Optional[int]:
    """Parse an optional integer form value."""
    value = (value or "").strip()
    if not value:
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc


def parse_json_or_empty(text: str) -> Dict[str, Any]:
    """Parse an optional JSON object used for extra metadata fields."""
    text = (text or "").strip()
    if not text:
        return {}

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('Extra JSON must be a JSON object, for example {"field": "value"}.')

    return data


def normalize_date_from_picker(value: str) -> Optional[str]:
    """Convert an HTML date input value into the AIoD datetime string.

    The form uses <input type="date">, which returns YYYY-MM-DD.
    AIoD examples use YYYY-MM-DDTHH:MM:SS.000.
    """
    value = (value or "").strip()
    if not value:
        return None

    # Already a datetime-like value: keep it as provided.
    if "T" in value:
        return value

    # HTML date picker format.
    if len(value) == 10:
        return f"{value}T00:00:00.000"

    return value

def normalize_description_for_aiod(value: Any) -> Optional[Dict[str, str]]:
    """Convert form description text into the AIoD description structure.

    AIoD assets expose description as:
    {
      "plain": "...",
      "html": "..."
    }

    Sending a raw string can be accepted by some endpoints but later appear as
    description: {} when reading the asset back.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        plain = str(value.get("plain") or value.get("text") or value.get("value") or "").strip()
        html = str(value.get("html") or "").strip()
    else:
        plain = str(value).strip()
        html = ""

    if not plain and not html:
        return None

    return {
        "plain": plain,
        "html": html,
    }


def normalize_description_from_form(form: Any) -> Optional[Dict[str, str]]:
    """Build the AIoD description object from dedicated plain/html form fields."""
    plain = str(form.get("description_plain") or form.get("description") or "").strip()
    html = str(form.get("description_html") or "").strip()

    if not plain and not html:
        return None

    return {
        "plain": plain,
        "html": html,
    }
def parse_json_field_or_default(text: str, default: Any, field_name: str) -> Any:
    """Parse a JSON field from a textarea, returning default when empty."""
    text = (text or "").strip()

    if not text:
        return default

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name} must contain valid JSON. Error: {exc}"
        ) from exc


def parse_json_array_field(text: str, field_name: str) -> List[Any]:
    """Parse a JSON textarea expected to contain an array."""
    data = parse_json_field_or_default(text, [], field_name)

    if not isinstance(data, list):
        raise ValueError(
            f"{field_name} must be a JSON array, for example []."
        )

    return data


def parse_json_object_field(text: str, field_name: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON textarea expected to contain an object or empty/null."""
    data = parse_json_field_or_default(text, None, field_name)

    if data is None:
        return None

    if not isinstance(data, dict):
        raise ValueError(
            f"{field_name} must be a JSON object, for example {{}}."
        )

    return data


def normalize_datetime_from_picker(value: str) -> Optional[str]:
    """Convert datetime-local input into the AIoD datetime string."""
    value = (value or "").strip()
    if not value:
        return None

    if "T" not in value:
        return normalize_date_from_picker(value)

    if len(value) == 16:
        return f"{value}:00.000"

    if len(value) == 19:
        return f"{value}.000"

    return value


def datetime_for_input(value: Any) -> str:
    """Convert an AIoD datetime string into an HTML datetime-local value."""
    text = str(value or "").strip()
    if not text:
        return ""

    if text.endswith("Z"):
        text = text[:-1]

    if "." in text:
        text = text.split(".", 1)[0]

    if len(text) >= 16 and "T" in text:
        return text[:16]

    return text


def build_resource_items_from_form(form: Any, prefix: str, integer_label: str) -> Optional[List[Dict[str, Any]]]:
    """Build distribution/media objects from dedicated repeated form fields."""
    media_fields = {
        "platform": form_repeated_values(form, f"{prefix}_platform"),
        "platform_resource_identifier": form_repeated_values(form, f"{prefix}_platform_resource_identifier"),
        "checksum": form_repeated_values(form, f"{prefix}_checksum"),
        "checksum_algorithm": form_repeated_values(form, f"{prefix}_checksum_algorithm"),
        "copyright": form_repeated_values(form, f"{prefix}_copyright"),
        "content_url": form_repeated_values(form, f"{prefix}_content_url"),
        "content_size_kb": form_repeated_values(form, f"{prefix}_content_size_kb"),
        "date_published": form_repeated_values(form, f"{prefix}_date_published"),
        "description": form_repeated_values(form, f"{prefix}_description"),
        "encoding_format": form_repeated_values(form, f"{prefix}_encoding_format"),
        "name": form_repeated_values(form, f"{prefix}_name"),
        "technology_readiness_level": form_repeated_values(form, f"{prefix}_technology_readiness_level"),
        "binary_blob": form_repeated_values(form, f"{prefix}_binary_blob"),
    }

    max_len = max((len(values) for values in media_fields.values()), default=0)
    if not max_len:
        return None

    items: List[Dict[str, Any]] = []

    for index in range(max_len):
        item: Dict[str, Any] = {}

        for key in (
            "platform",
            "platform_resource_identifier",
            "checksum",
            "checksum_algorithm",
            "copyright",
            "content_url",
            "description",
            "encoding_format",
            "name",
            "binary_blob",
        ):
            value = media_fields[key][index] if index < len(media_fields[key]) else ""
            if value:
                item[key] = value

        content_size = (
            media_fields["content_size_kb"][index]
            if index < len(media_fields["content_size_kb"])
            else ""
        )
        parsed_size = parse_optional_int(content_size, f"{integer_label} content_size_kb")
        if parsed_size is not None:
            item["content_size_kb"] = parsed_size

        trl = (
            media_fields["technology_readiness_level"][index]
            if index < len(media_fields["technology_readiness_level"])
            else ""
        )
        parsed_trl = parse_optional_int(trl, f"{integer_label} technology_readiness_level")
        if parsed_trl is not None:
            item["technology_readiness_level"] = parsed_trl

        published = (
            media_fields["date_published"][index]
            if index < len(media_fields["date_published"])
            else ""
        )
        normalized_published = normalize_datetime_from_picker(published)
        if normalized_published:
            item["date_published"] = normalized_published

        if item:
            items.append(item)

    return items


def build_media_items_from_form(form: Any) -> Optional[List[Dict[str, Any]]]:
    """Build media objects from the dedicated media form fields."""
    return build_resource_items_from_form(form, "media", "media")


def build_distribution_items_from_form(form: Any) -> Optional[List[Dict[str, Any]]]:
    """Build distribution objects from the dedicated distribution form fields."""
    return build_resource_items_from_form(form, "distribution", "distribution")


def build_note_items_from_form(form: Any) -> Optional[List[Dict[str, Any]]]:
    """Build note objects from the dedicated note form fields."""
    values = form_repeated_values(form, "note_value")
    if not values:
        return None

    items = [
        {"value": value}
        for value in values
        if value
    ]

    return items


# ---------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------


def normalize_controlled_vocabulary_options(raw: Any) -> List[Dict[str, str]]:
    """Convert a controlled-vocabulary API response into select options."""
    if isinstance(raw, dict):
        for key in ("items", "results", "data", "application_areas", "computational_asset_types"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raw = list(raw.values())

    if not isinstance(raw, list):
        return []

    options: List[Dict[str, str]] = []
    seen = set()

    for item in raw:
        if isinstance(item, str):
            value = item.strip()
            label = value
        elif isinstance(item, dict):
            value = str(
                item.get("name")
                or item.get("label")
                or item.get("term")
                or item.get("value")
                or item.get("identifier")
                or item.get("id")
                or ""
            ).strip()
            label = str(item.get("label") or item.get("name") or value).strip()
        else:
            value = str(item).strip()
            label = value

        if not value or value in seen:
            continue

        seen.add(value)
        options.append({
            "value": value,
            "label": label or value,
        })

    return options


def normalize_research_area_terms(raw: Any) -> List[Dict[str, Any]]:
    """Normalize the nested research-area vocabulary returned by AIoD."""
    if isinstance(raw, dict):
        for key in ("items", "results", "data", "research_areas"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break

    if not isinstance(raw, list):
        return []

    def normalize_node(node: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return None

        term = str(node.get("term") or "").strip()
        if not term:
            return None

        subterms = [
            normalized
            for child in (node.get("subterms") or [])
            if (normalized := normalize_node(child)) is not None
        ]

        return {
            "term": term,
            "definition": str(node.get("definition") or "").strip(),
            "subterms": subterms,
        }

    return [
        normalized
        for item in raw
        if (normalized := normalize_node(item)) is not None
    ]


@lru_cache(maxsize=8)
def fetch_controlled_vocabulary_options(url: str) -> Tuple[Dict[str, str], ...]:
    """Fetch and cache controlled-vocabulary terms from an AIoD REST endpoint."""
    session = requests.Session()
    session.trust_env = False

    response = session.get(
        url,
        headers={"accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    return tuple(normalize_controlled_vocabulary_options(response.json()))


@lru_cache(maxsize=8)
def fetch_research_area_terms(url: str) -> Tuple[Dict[str, Any], ...]:
    """Fetch and cache the nested AIoD research-area vocabulary."""
    session = requests.Session()
    session.trust_env = False

    response = session.get(
        url,
        headers={"accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    return tuple(normalize_research_area_terms(response.json()))


@lru_cache(maxsize=1)
def get_application_area_options() -> List[Dict[str, str]]:
    """Return AIoD application-area options for form multi-select fields."""
    try:
        return sorted(
            fetch_controlled_vocabulary_options(APPLICATION_AREAS_URL),
            key=lambda option: option["label"].casefold(),
        )
    except Exception:
        return []


@lru_cache(maxsize=1)
def get_research_area_terms() -> List[Dict[str, Any]]:
    """Return nested AIoD research-area terms for options and information modal."""
    try:
        return list(fetch_research_area_terms(RESEARCH_AREAS_URL))
    except Exception:
        return []


def get_research_area_options() -> List[Dict[str, str]]:
    """Return top-level AIoD research-area options for form multi-select fields."""
    return sorted([
        {
            "value": item["term"],
            "label": item["term"],
        }
        for item in get_research_area_terms()
        if item.get("term")
    ], key=lambda option: option["label"].casefold())


@lru_cache(maxsize=1)
def get_industrial_sector_terms() -> List[Dict[str, Any]]:
    """Return nested AIoD industrial-sector terms for options and information modal."""
    try:
        return list(fetch_research_area_terms(INDUSTRIAL_SECTORS_URL))
    except Exception:
        return []


def get_industrial_sector_options() -> List[Dict[str, str]]:
    """Return top-level AIoD industrial-sector options for form multi-select fields."""
    return sorted([
        {
            "value": item["term"],
            "label": item["term"],
        }
        for item in get_industrial_sector_terms()
        if item.get("term")
    ], key=lambda option: option["label"].casefold())


@lru_cache(maxsize=1)
def get_license_terms() -> List[Dict[str, Any]]:
    """Return AIoD license terms for the license select field."""
    try:
        return list(fetch_research_area_terms(LICENSES_URL))
    except Exception:
        return []


def get_license_options() -> List[Dict[str, str]]:
    """Return AIoD license options for single-select form fields."""
    return sorted([
        {
            "value": item["term"],
            "label": item["term"],
        }
        for item in get_license_terms()
        if item.get("term")
    ], key=lambda option: option["label"].casefold())


@lru_cache(maxsize=1)
def get_computational_asset_type_options() -> List[Dict[str, str]]:
    """Return AIoD computational asset type options for single-select form fields."""
    try:
        return sorted(
            fetch_controlled_vocabulary_options(COMPUTATIONAL_ASSET_TYPES_URL),
            key=lambda option: option["label"].casefold(),
        )
    except Exception:
        return []


@lru_cache(maxsize=1)
def get_scientific_domain_terms() -> List[Dict[str, Any]]:
    """Return nested AIoD scientific-domain terms for options and information modal."""
    try:
        return list(fetch_research_area_terms(SCIENTIFIC_DOMAINS_URL))
    except Exception:
        return []


def get_scientific_domain_options() -> List[Dict[str, str]]:
    """Return top-level AIoD scientific-domain options for form multi-select fields."""
    return sorted([
        {
            "value": item["term"],
            "label": item["term"],
        }
        for item in get_scientific_domain_terms()
        if item.get("term")
    ], key=lambda option: option["label"].casefold())
    
def build_computational_asset_metadata(form: Dict[str, Any]) -> Dict[str, Any]:
    """Build an AIoD computational asset metadata payload from submitted form data."""
    project_identifier = (form.get("project_identifier") or "").strip()
    extra = parse_json_or_empty(form.get("extra_json") or "")
    distribution_items = build_distribution_items_from_form(form)
    media_items = build_media_items_from_form(form)
    note_items = build_note_items_from_form(form)

    is_part_of = split_lines(form.get("is_part_of") or "")
    if project_identifier and project_identifier not in is_part_of:
        is_part_of.insert(0, project_identifier)

    metadata: Dict[str, Any] = {
        "platform": (form.get("platform") or "").strip() or None,
        "platform_resource_identifier": (form.get("platform_resource_identifier") or "").strip() or None,
        "name": (form.get("name") or "").strip(),
        "date_published": normalize_date_from_picker(form.get("date_published") or ""),
        "same_as": (form.get("same_as") or "").strip() or None,
        "is_accessible_for_free": form.get("is_accessible_for_free") == "on",
        "version": (form.get("asset_version") or "").strip() or None,
        "status_info": (form.get("status_info") or "").strip() or None,
        "aiod_entry": parse_json_object_field(form.get("aiod_entry_json") or "", "aiod_entry_json"),
        "alternate_name": split_lines(form.get("alternate_name") or ""),
        "application_area": form_list_values(form, "application_area"),
        "citation": split_lines(form.get("citation") or ""),
        "contact": split_lines(form.get("contact") or ""),
        "creator": split_lines(form.get("creator") or ""),
        "description": normalize_description_from_form(form),
        "distribution": distribution_items if distribution_items is not None else parse_json_array_field(form.get("distribution_json") or "", "distribution_json"),
        "has_part": split_lines(form.get("has_part") or ""),
        "industrial_sector": form_list_values(form, "industrial_sector"),
        "is_part_of": is_part_of,
        "keyword": split_lines(form.get("keyword") or ""),
        "license": (form.get("license") or "").strip() or None,
        "media": media_items if media_items is not None else parse_json_array_field(form.get("media_json") or "", "media_json"),
        "note": note_items if note_items is not None else parse_json_array_field(form.get("note_json") or "", "note_json"),
        "relevant_link": split_lines(form.get("relevant_link") or ""),
        "relevant_resource": split_lines(form.get("relevant_resource") or ""),
        "relevant_to": split_lines(form.get("relevant_to") or ""),
        "research_area": form_list_values(form, "research_area"),
        "scientific_domain": form_list_values(form, "scientific_domain"),
        "type": (form.get("asset_type") or "").strip() or None,
    }

    metadata.update(extra)

    # Remove only empty optional scalars and null objects.
    # Keep arrays and booleans because the AIoD schema accepts empty arrays.
    for key in list(metadata.keys()):
        if metadata[key] is None:
            metadata.pop(key)

    return metadata


# ---------------------------------------------------------------------
# Computational Asset SDK wrappers
# ---------------------------------------------------------------------


def register_computational_asset(metadata: Dict[str, Any], version: Optional[str]) -> Any:
    """Register a computational asset through the AIoD SDK."""
    version = apply_version(version)
    kwargs = {"metadata": metadata}
    if version:
        kwargs["version"] = version
    return aiod.computational_assets.register(**kwargs)


def get_computational_asset(identifier: str, version: Optional[str]) -> Any:
    """Retrieve one computational asset through the AIoD SDK."""
    version = apply_version(version)
    kwargs = {"identifier": identifier, "data_format": "json"}
    if version:
        kwargs["version"] = version
    return aiod.computational_assets.get_asset(**kwargs)


def delete_computational_asset(identifier: str, version: Optional[str]) -> Any:
    """Delete one computational asset through the AIoD SDK."""
    version = apply_version(version)
    kwargs = {"identifier": identifier}
    if version:
        kwargs["version"] = version
    return aiod.computational_assets.delete(**kwargs)


def asset_identifier(asset: Dict[str, Any]) -> str:
    """Extract an identifier from a computational asset response."""
    for key in ("identifier", "ai_resource_identifier", "asset_identifier", "platform_resource_identifier"):
        if asset.get(key):
            return str(asset[key])

    entry = asset.get("aiod_entry")
    if isinstance(entry, dict):
        for key in ("identifier", "id", "asset_identifier"):
            if entry.get(key):
                return str(entry[key])

    return ""


def asset_name(asset: Dict[str, Any]) -> str:
    """Return the best display name for a computational asset."""
    for key in ("name", "title", "alternate_name"):
        value = asset.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if value:
            return str(value)

    return asset_identifier(asset) or "<unnamed>"


def asset_status(asset: Dict[str, Any]) -> str:
    """Extract a publication or workflow status from an asset response."""
    entry = asset.get("aiod_entry")
    if isinstance(entry, dict):
        for key in ("status", "publication_status", "state"):
            if entry.get(key):
                return str(entry[key])

    for key in ("status", "publication_status", "state"):
        if asset.get(key):
            return str(asset[key])

    return ""


def computational_asset_summary(asset: Dict[str, Any]) -> Dict[str, str]:
    """Build the compact asset row used by catalogue and diagnostics views."""
    return {
        "identifier": asset_identifier(asset),
        "name": asset_name(asset),
        "same_as": str(asset.get("same_as") or ""),
        "version": str(asset.get("version") or ""),
        "status": asset_status(asset),
        "is_part_of": safe_json(asset.get("is_part_of") or []),
        "raw": safe_json(asset),
    }


def list_computational_assets(version: Optional[str], limit: int = 50, max_pages: int = 5) -> Dict[str, Any]:
    """List visible AIoD computational assets across a bounded number of pages."""
    version = apply_version(version)
    diagnostics: List[str] = []
    raw_blocks: List[Dict[str, Any]] = []
    results: List[Dict[str, str]] = []
    total = 0

    for page in range(max_pages):
        offset = page * limit

        try:
            kwargs = {"offset": offset, "limit": limit, "data_format": "json"}
            if version:
                kwargs["version"] = version

            raw = aiod.computational_assets.get_list(**kwargs)
            items = normalize_items(raw)
            total += len(items)

            raw_blocks.append({
                "method": f"computational_assets.get_list offset={offset}",
                "items_count": len(items),
                "raw_preview": safe_json(raw)[:3000],
            })

            for item in items:
                results.append(computational_asset_summary(item))

            if len(items) < limit:
                break
        except Exception as exc:
            diagnostics.append(f"computational_assets.get_list offset={offset}: ERROR {type(exc).__name__}: {exc}")
            raw_blocks.append({
                "method": f"computational_assets.get_list offset={offset}",
                "error": traceback.format_exc(),
            })
            break

    diagnostics.append(f"computational_assets.get_list: total items read: {total}")

    return {
        "version": version or "default SDK version",
        "results": results,
        "diagnostics": diagnostics,
        "raw_blocks": raw_blocks,
    }


def search_computational_assets(query: str, version: Optional[str], limit: int = 50) -> Dict[str, Any]:
    """Search visible computational assets by locally filtering SDK list results."""
    query = (query or "").strip()
    q_lower = query.lower()

    data = list_computational_assets(version=version, limit=limit, max_pages=6)

    if q_lower:
        data["results"] = [
            item for item in data["results"]
            if q_lower in text_of(item).lower()
        ]

    data["query"] = query
    return data


def verify_computational_asset_creation(
    metadata: Dict[str, Any],
    raw_result: Any,
    version: Optional[str],
) -> Dict[str, Any]:
    """Confirm registration as strongly as possible using SDK-only calls.

    A confirmed result means either:
    - register returned an identifier and get_asset(identifier) works, or
    - no identifier was returned, but get_list shows an asset matching name/same_as/is_part_of.
    """
    version = apply_version(version)
    identifier = extract_identifier(raw_result)
    checks: List[Dict[str, Any]] = []

    if identifier:
        try:
            asset = get_computational_asset(identifier, version)
            checks.append({
                "check": "get_asset_by_returned_identifier",
                "ok": True,
                "asset": computational_asset_summary(asset) if isinstance(asset, dict) else safe_json(asset),
            })
            return {
                "confirmed": True,
                "confidence": "high",
                "identifier": identifier,
                "reason": "The SDK returned an identifier and get_asset(identifier) retrieved the asset.",
                "checks": checks,
            }
        except Exception as exc:
            checks.append({
                "check": "get_asset_by_returned_identifier",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            })
            return {
                "confirmed": False,
                "confidence": "low",
                "identifier": identifier,
                "reason": "The SDK returned an identifier, but get_asset(identifier) could not retrieve it.",
                "checks": checks,
            }

    # No identifier: fallback by list and exact metadata matching.
    try:
        listed = list_computational_assets(version=version, limit=50, max_pages=8)
        candidates = []

        target_name = str(metadata.get("name") or "").strip().lower()
        target_same_as = str(metadata.get("same_as") or "").strip().lower()
        target_project_ids = {
            str(x).strip()
            for x in (metadata.get("is_part_of") or [])
            if str(x).strip()
        }

        for row in listed.get("results", []):
            raw_text = (row.get("raw") or "").lower()
            score = 0

            if target_name and target_name == str(row.get("name") or "").strip().lower():
                score += 5
            elif target_name and target_name in raw_text:
                score += 2

            if target_same_as and target_same_as == str(row.get("same_as") or "").strip().lower():
                score += 5
            elif target_same_as and target_same_as in raw_text:
                score += 2

            if target_project_ids and any(pid.lower() in raw_text for pid in target_project_ids):
                score += 2

            if score >= 5:
                row2 = dict(row)
                row2["match_score"] = str(score)
                candidates.append(row2)

        checks.append({
            "check": "get_list_match_by_metadata",
            "ok": bool(candidates),
            "candidates": candidates[:10],
            "diagnostics": listed.get("diagnostics"),
            "raw_blocks": listed.get("raw_blocks")[:2],
        })

        if candidates:
            best = candidates[0]
            return {
                "confirmed": True,
                "confidence": "medium",
                "identifier": best.get("identifier", ""),
                "reason": (
                    "register() did not return an identifier, but get_list() shows "
                    "an asset compatible with name/same_as/is_part_of."
                ),
                "checks": checks,
            }
    except Exception as exc:
        checks.append({
            "check": "get_list_match_by_metadata",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })

    return {
        "confirmed": False,
        "confidence": "low",
        "identifier": "",
        "reason": (
            "register() did not return an identifier and no compatible asset "
            "was found through get_list(). Creation is not confirmed."
        ),
        "checks": checks,
    }


# ---------------------------------------------------------------------
# Local transaction log
# ---------------------------------------------------------------------


def write_transaction_log(
    payload: Dict[str, Any],
    raw_result: Any,
    sdk_result_description: Dict[str, Any],
    verification: Dict[str, Any],
) -> None:
    """Append one registration attempt to the local JSONL transaction log."""
    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
        "sdk_result": sdk_result_description,
        "verification": verification,
    }

    Path("aiod_upload_transactions.jsonl").open("a", encoding="utf-8").write(
        json.dumps(log, ensure_ascii=False, default=str) + "\n"
    )


def local_uploaded_assets_from_log(path: str = "aiod_upload_transactions.jsonl") -> Dict[str, Any]:
    """Read locally created assets from the app transaction log.

    This is not an AIoD 'my assets' endpoint. It only lists assets registered
    through this local uploader instance.
    """
    log_path = Path(path)

    if not log_path.exists():
        return {
            "results": [],
            "diagnostics": [
                f"No local log file found: {path}. Only assets created after logging was introduced will be shown."
            ],
        }

    rows: List[Dict[str, Any]] = []
    diagnostics: List[str] = []
    seen = set()

    for line_no, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except Exception as exc:
            diagnostics.append(f"Line {line_no}: invalid JSON ({type(exc).__name__}: {exc})")
            continue

        payload = entry.get("payload") or {}
        verification = entry.get("verification") or {}
        sdk_result = entry.get("sdk_result") or {}

        identifier = (
            verification.get("identifier")
            or sdk_result.get("identifier")
            or extract_identifier(sdk_result)
            or ""
        )

        if not identifier:
            continue

        if identifier in seen:
            continue

        seen.add(identifier)

        submission = entry.get("submission") or {}
        submission_result = submission.get("result") or {}
        submission_json = submission_result.get("http_json") or {}

        submission_identifier = (
            submission_json.get("submission_identifier")
            or submission_json.get("identifier")
            or ""
        )

        rows.append({
            "timestamp_utc": str(entry.get("timestamp_utc") or ""),
            "identifier": identifier,
            "name": str(payload.get("name") or ""),
            "same_as": str(payload.get("same_as") or ""),
            "version": str(payload.get("version") or ""),
            "project": safe_json(payload.get("is_part_of") or []),
            "confirmed": str(bool(verification.get("confirmed"))),
            "confidence": str(verification.get("confidence") or ""),
            "submitted": str(bool(submission)),
            "submission_identifier": str(submission_identifier),
            "submitted_at": str(submission.get("timestamp_utc") or ""),
            "raw": safe_json(entry),
        })

    return {
        "results": rows,
        "diagnostics": diagnostics,
    }

def _log_entry_identifier(entry: Dict[str, Any]) -> str:
    """Extract an asset identifier from a local transaction-log entry."""
    payload = entry.get("payload") or {}
    verification = entry.get("verification") or {}
    sdk_result = entry.get("sdk_result") or {}

    identifier = (
        verification.get("identifier")
        or sdk_result.get("identifier")
        or extract_identifier(sdk_result)
        or ""
    )

    if identifier:
        return str(identifier)

    # Fallback: sometimes the identifier may be present only in raw serialized content.
    raw = safe_json(entry)
    for prefix in ("comp_", "proj_"):
        idx = raw.find(prefix)
        if idx >= 0:
            candidate = raw[idx:].split('"')[0].split("'")[0].split()[0].split(",")[0]
            return candidate

    return ""


def remove_local_uploaded_asset(identifier: str, path: str = "aiod_upload_transactions.jsonl") -> Dict[str, Any]:
    """Remove an asset from the local transaction log.

    This does not delete anything from AIoD. It only removes local history rows
    matching the given asset identifier.
    """
    identifier = (identifier or "").strip()
    log_path = Path(path)

    if not identifier:
        return {
            "removed": 0,
            "kept": 0,
            "message": "No identifier provided.",
        }

    if not log_path.exists():
        return {
            "removed": 0,
            "kept": 0,
            "message": f"Local log file not found: {path}",
        }

    kept_lines: List[str] = []
    removed = 0
    invalid_lines = 0

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
            entry_identifier = _log_entry_identifier(entry)
        except Exception:
            # Keep invalid lines rather than destroying unknown user data.
            invalid_lines += 1
            kept_lines.append(line)
            continue

        if entry_identifier == identifier:
            removed += 1
        else:
            kept_lines.append(line)

    log_path.write_text(
        "\n".join(kept_lines) + ("\n" if kept_lines else ""),
        encoding="utf-8",
    )

    return {
        "removed": removed,
        "kept": len(kept_lines),
        "invalid_lines_kept": invalid_lines,
        "message": (
            f"Removed {removed} local log entr{'y' if removed == 1 else 'ies'} "
            f"for identifier {identifier}."
        ),
    }


def format_exception_for_ui(exc: Exception) -> Dict[str, Any]:
    """Return a compact, readable exception payload for the UI."""
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }

def _find_key_recursive(data: Any, target_key: str) -> Optional[str]:
    """Find a key recursively inside nested dict/list data."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key == target_key and value:
                return str(value)

            found = _find_key_recursive(value, target_key)
            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = _find_key_recursive(item, target_key)
            if found:
                return found

    return None


def read_aiod_token_field_from_toml(field_names: List[str]) -> str:
    """Read a token field from ~/.aiod/token.toml."""
    token_path = Path.home() / ".aiod" / "token.toml"

    if not token_path.exists():
        raise RuntimeError(
            f"AIoD token file not found at {token_path}. "
            "Open the Auth page and run authentication first."
        )

    with token_path.open("rb") as f:
        token_data = tomllib.load(f)

    for field_name in field_names:
        value = _find_key_recursive(token_data, field_name)
        if value:
            return value

    raise RuntimeError(
        f"Could not find any of these token fields inside {token_path}: {field_names}. "
        "Open the Auth page, clear the old token, and authenticate again."
    )


def refresh_aiod_access_token() -> str:
    """Use the refresh token from token.toml to obtain a fresh access token.

    This keeps submission/retract as REST calls, but avoids using a stale access_token.
    """
    refresh_token = read_aiod_token_field_from_toml([
        "refresh_token",
        "refreshToken",
    ])

    auth_server = str(getattr(aiod.config, "auth_server", "https://auth.aiodp.eu/aiod-auth/")).rstrip("/")
    client_id = str(getattr(aiod.config, "client_id", "aiod-sdk"))

    token_url = f"{auth_server}/realms/aiod/protocol/openid-connect/token"

    response = requests.post(
        token_url,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        },
        headers={
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )

    try:
        token_json = response.json()
    except Exception:
        token_json = {}

    if response.status_code == 401 or response.status_code == 400:
        raise RuntimeError(
            "AIoD refresh token is expired or invalid. "
            "Go to Auth check, run Start authentication again, then retry. "
            f"Server response: {response.text}"
        )

    if not response.ok:
        raise RuntimeError(
            f"AIoD token refresh failed with HTTP {response.status_code}: {response.text}"
        )

    access_token = token_json.get("access_token")

    if not access_token:
        raise RuntimeError(
            f"AIoD token refresh did not return an access_token. Server response: {response.text}"
        )

    return str(access_token)


def read_aiod_access_token_from_toml() -> str:
    """Fallback only: read the current access token from token.toml."""
    return read_aiod_token_field_from_toml([
        "access_token",
        "accessToken",
    ])


def aiod_rest_headers(content_type_json: bool = True) -> Dict[str, str]:
    """Build REST headers using a fresh access token whenever possible."""
    try:
        access_token = refresh_aiod_access_token()
    except Exception:
        # Fallback: useful only if refresh is unavailable but access_token is still valid.
        access_token = read_aiod_access_token_from_toml()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "accept": "application/json",
    }

    if content_type_json:
        headers["Content-Type"] = "application/json"

    return headers

def current_rest_user() -> Tuple[bool, str]:
    """Check whether REST-protected endpoints can be called with a fresh token."""
    try:
        url = f"{aiod_rest_base_url()}/submissions"

        response = requests.get(
            url,
            headers=aiod_rest_headers(content_type_json=False),
            timeout=30,
        )

        if response.status_code == 401:
            return (
                False,
                "REST token is expired or invalid. "
                f"Server response: {response.text}",
            )

        if response.status_code == 403:
            return (
                False,
                "REST token is valid, but this account may not have permission "
                f"for this endpoint. Server response: {response.text}",
            )

        if not response.ok:
            return (
                False,
                f"REST auth check failed with HTTP {response.status_code}: {response.text}",
            )

        return True, f"REST token is valid. HTTP {response.status_code}."

    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

def aiod_rest_base_url() -> str:
    """Return AIoD API base URL."""
    return str(aiod.config.api_server).rstrip("/")

def submit_assets_for_review(
    asset_identifiers: List[str],
    comment: str = "",
) -> Dict[str, Any]:
    """Submit one or more AIoD assets for review via REST API."""
    cleaned_identifiers = [
        str(identifier).strip()
        for identifier in asset_identifiers
        if str(identifier).strip()
    ]

    if not cleaned_identifiers:
        raise ValueError("At least one asset identifier is required for submission.")

    comment = (comment or "").strip()
    if len(comment) > 256:
        comment = comment[:256]

    url = f"{aiod_rest_base_url()}/submissions"

    payload: Dict[str, Any] = {
        "asset_identifiers": cleaned_identifiers,
    }

    if comment:
        payload["comment"] = comment

    response = requests.post(
        url,
        headers=aiod_rest_headers(content_type_json=True),
        json=payload,
        timeout=30,
    )

    result: Dict[str, Any] = {
        "url": url,
        "request_payload": payload,
        "http_status_code": response.status_code,
        "http_ok": response.ok,
        "http_text": response.text,
    }

    try:
        result["http_json"] = response.json()
    except Exception as exc:
        result["http_json_error"] = f"{type(exc).__name__}: {exc}"

    if response.status_code == 401:
        raise RuntimeError(
            "AIoD authentication expired or invalid. "
            "Go to Auth check, run Start authentication again, then retry. "
            f"Server response: {response.text}"
        )

    if not response.ok:
        raise RuntimeError(
            f"AIoD submission failed with HTTP {response.status_code}: {response.text}"
        )

    return result

def list_submissions() -> Dict[str, Any]:
    """List AIoD submissions via REST API."""
    url = f"{aiod_rest_base_url()}/submissions"

    response = requests.get(
        url,
        headers=aiod_rest_headers(content_type_json=False),
        timeout=30,
    )

    result: Dict[str, Any] = {
        "url": url,
        "http_status_code": response.status_code,
        "http_ok": response.ok,
        "http_text": response.text,
    }

    try:
        result["http_json"] = response.json()
    except Exception as exc:
        result["http_json_error"] = f"{type(exc).__name__}: {exc}"

    if response.status_code == 401:
        raise RuntimeError(
            "AIoD authentication expired or invalid. "
            "Go to Auth check, run Start authentication again, then retry. "
            f"Server response: {response.text}"
        )

    if not response.ok:
        raise RuntimeError(
            f"AIoD submissions list failed with HTTP {response.status_code}: {response.text}"
        )

    return result


def append_submission_to_local_asset(
    asset_identifier: str,
    submission_result: Dict[str, Any],
    path: str = "aiod_upload_transactions.jsonl",
) -> Dict[str, Any]:
    """Store submission information in the local transaction log.

    This only updates the local history file. It does not affect AIoD.
    """
    asset_identifier = (asset_identifier or "").strip()
    log_path = Path(path)

    if not asset_identifier:
        return {
            "updated": 0,
            "message": "No asset identifier provided.",
        }

    if not log_path.exists():
        return {
            "updated": 0,
            "message": f"Local log file not found: {path}",
        }

    updated = 0
    kept_lines: List[str] = []

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
            entry_identifier = _log_entry_identifier(entry)

            if entry_identifier == asset_identifier:
                entry["submission"] = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "result": submission_result,
                }
                updated += 1

            kept_lines.append(json.dumps(entry, ensure_ascii=False, default=str))

        except Exception:
            # Keep malformed lines untouched.
            kept_lines.append(line)

    log_path.write_text(
        "\n".join(kept_lines) + ("\n" if kept_lines else ""),
        encoding="utf-8",
    )

    return {
        "updated": updated,
        "message": f"Updated {updated} local log entr{'y' if updated == 1 else 'ies'} for {asset_identifier}.",
    }


def retract_submission(submission_identifier: str) -> Dict[str, Any]:
    """Retract an AIoD submission via REST API."""
    submission_identifier = (submission_identifier or "").strip()

    if not submission_identifier:
        raise ValueError("Submission identifier is required to retract a submission.")

    url = f"{aiod_rest_base_url()}/submissions/retract/{submission_identifier}"

    response = requests.post(
        url,
        headers=aiod_rest_headers(content_type_json=False),
        timeout=30,
    )

    result: Dict[str, Any] = {
        "url": url,
        "submission_identifier": submission_identifier,
        "http_status_code": response.status_code,
        "http_ok": response.ok,
        "http_text": response.text,
    }

    try:
        result["http_json"] = response.json()
    except Exception as exc:
        result["http_json_error"] = f"{type(exc).__name__}: {exc}"

    if response.status_code == 401:
        raise RuntimeError(
            "AIoD authentication expired or invalid. "
            "Go to Auth check, run Start authentication again, then retry. "
            f"Server response: {response.text}"
        )

    if not response.ok:
        raise RuntimeError(
            f"AIoD retract failed with HTTP {response.status_code}: {response.text}"
        )

    return result


def mark_local_asset_retracted(
    asset_identifier: str,
    retract_result: Dict[str, Any],
    path: str = "aiod_upload_transactions.jsonl",
) -> Dict[str, Any]:
    """Mark a local asset as retracted in the transaction log.

    After retract, the local card should behave like a draft again:
    Submit enabled, Delete enabled, Retract hidden.
    """
    asset_identifier = (asset_identifier or "").strip()
    log_path = Path(path)

    if not asset_identifier:
        return {
            "updated": 0,
            "message": "No asset identifier provided.",
        }

    if not log_path.exists():
        return {
            "updated": 0,
            "message": f"Local log file not found: {path}",
        }

    updated = 0
    kept_lines: List[str] = []

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
            entry_identifier = _log_entry_identifier(entry)

            if entry_identifier == asset_identifier:
                old_submission = entry.get("submission")
                entry["submission_retracted"] = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "previous_submission": old_submission,
                    "result": retract_result,
                }

                # Remove active submission so the UI goes back to draft-like state.
                entry.pop("submission", None)
                updated += 1

            kept_lines.append(json.dumps(entry, ensure_ascii=False, default=str))

        except Exception:
            kept_lines.append(line)

    log_path.write_text(
        "\n".join(kept_lines) + ("\n" if kept_lines else ""),
        encoding="utf-8",
    )

    return {
        "updated": updated,
        "message": f"Marked {updated} local entr{'y' if updated == 1 else 'ies'} as retracted for {asset_identifier}.",
    }

def find_local_asset_identifier_by_submission(
    submission_identifier: str,
    path: str = "aiod_upload_transactions.jsonl",
) -> str:
    """Find the local asset identifier linked to a submission identifier."""
    submission_identifier = (submission_identifier or "").strip()
    log_path = Path(path)

    if not submission_identifier or not log_path.exists():
        return ""

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except Exception:
            continue

        submission = entry.get("submission") or {}
        submission_result = submission.get("result") or {}
        submission_json = submission_result.get("http_json") or {}

        stored_submission_identifier = (
            submission_json.get("submission_identifier")
            or submission_json.get("identifier")
            or ""
        )

        if str(stored_submission_identifier) == submission_identifier:
            return _log_entry_identifier(entry)

    return ""

def update_computational_asset_via_rest(
    identifier: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Update an existing computational asset via REST PUT.

    Uses PUT /computational_assets/{identifier}.
    Treat this as a full metadata update.
    """
    identifier = (identifier or "").strip()

    if not identifier:
        raise ValueError("Computational asset identifier is required.")

    url = f"{aiod_rest_base_url()}/computational_assets/{identifier}"

    response = requests.put(
        url,
        headers=aiod_rest_headers(content_type_json=True),
        json=metadata,
        timeout=30,
    )

    result: Dict[str, Any] = {
        "url": url,
        "identifier": identifier,
        "request_payload": metadata,
        "http_status_code": response.status_code,
        "http_ok": response.ok,
        "http_text": response.text,
    }

    try:
        result["http_json"] = response.json()
    except Exception as exc:
        result["http_json_error"] = f"{type(exc).__name__}: {exc}"

    if response.status_code == 401:
        raise RuntimeError(
            "AIoD authentication expired or invalid. "
            "Go to Auth check, run Start authentication again, then retry. "
            f"Server response: {response.text}"
        )

    if not response.ok:
        raise RuntimeError(
            f"AIoD asset update failed with HTTP {response.status_code}: {response.text}"
        )

    return result


def asset_to_form_values(asset: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an AIoD computational asset JSON into form values for the edit modal."""

    def join_lines(value: Any) -> str:
        """Convert scalar or list values into newline-separated form text."""
        if isinstance(value, list):
            return "\n".join(str(x) for x in value if x is not None)
        if value is None:
            return ""
        return str(value)

    def first_text(value: Any) -> str:
        """Extract a readable plain text value from AIoD text fields."""
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, list):
            for item in value:
                text = first_text(item)
                if text:
                    return text
            return ""

        if isinstance(value, dict):
            for key in ("plain", "text", "value", "description", "content", "en", "it", "html"):
                text = first_text(value.get(key))
                if text:
                    return text
            return ""

        return str(value)

    def first_project(value: Any) -> str:
        """Return the first project identifier from an is_part_of field."""
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str):
            return value
        return ""

    def json_text(value: Any, default: Any) -> str:
        """Render nested JSON values for editable textarea fields."""
        if value is None:
            value = default
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)

    def resource_items(value: Any) -> List[Dict[str, Any]]:
        """Convert AIoD resource objects into values used by dedicated resource forms."""
        if not isinstance(value, list):
            return []

        items: List[Dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue

            items.append({
                "platform": str(item.get("platform") or ""),
                "platform_resource_identifier": str(item.get("platform_resource_identifier") or ""),
                "checksum": str(item.get("checksum") or ""),
                "checksum_algorithm": str(item.get("checksum_algorithm") or ""),
                "copyright": str(item.get("copyright") or ""),
                "content_url": str(item.get("content_url") or ""),
                "content_size_kb": str(item.get("content_size_kb") or ""),
                "date_published": datetime_for_input(item.get("date_published")),
                "description": str(item.get("description") or ""),
                "encoding_format": str(item.get("encoding_format") or ""),
                "name": str(item.get("name") or ""),
                "technology_readiness_level": str(item.get("technology_readiness_level") or ""),
                "binary_blob": str(item.get("binary_blob") or ""),
            })

        return items

    def note_items(value: Any) -> List[Dict[str, str]]:
        """Convert AIoD note objects into values used by the dedicated note form."""
        if not isinstance(value, list):
            return []

        items: List[Dict[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("value") or "").strip()
            else:
                text = str(item or "").strip()

            if text:
                items.append({"value": text})

        return items

    date_value = str(asset.get("date_published") or "")
    if "T" in date_value:
        date_value = date_value.split("T")[0]

    is_part_of = asset.get("is_part_of") or []

    return {
        "name": str(asset.get("name") or ""),
        "date_published": date_value,
        "same_as": str(asset.get("same_as") or ""),
        "is_accessible_for_free": "on" if bool(asset.get("is_accessible_for_free", True)) else "",
        "asset_version": str(asset.get("version") or ""),
        "alternate_name": join_lines(asset.get("alternate_name") or []),
        "application_area": join_lines(asset.get("application_area") or []),
        "citation": join_lines(asset.get("citation") or []),
        "contact": join_lines(asset.get("contact") or []),
        "creator": join_lines(asset.get("creator") or []),
        "description": first_text(
            asset.get("description")
            or asset.get("resource_description")
            or asset.get("abstract")
            or (asset.get("aiod_entry") or {}).get("description")
        ),
        "description_plain": first_text(
            (asset.get("description") or {}).get("plain")
            if isinstance(asset.get("description"), dict)
            else asset.get("description")
        ),
        "description_html": first_text(
            (asset.get("description") or {}).get("html")
            if isinstance(asset.get("description"), dict)
            else ""
        ),
        "distribution_items": resource_items(asset.get("distribution") or []),
        "distribution_json": json_text(asset.get("distribution") or [], []),
        "has_part": join_lines(asset.get("has_part") or []),
        "industrial_sector": join_lines(asset.get("industrial_sector") or []),
        "is_part_of": join_lines(is_part_of),
        "keyword": join_lines(asset.get("keyword") or []),
        "license": str(asset.get("license") or ""),
        "media_items": resource_items(asset.get("media") or []),
        "media_json": json_text(asset.get("media") or [], []),
        "note_items": note_items(asset.get("note") or []),
        "note_json": json_text(asset.get("note") or [], []),
        "relevant_link": join_lines(asset.get("relevant_link") or []),
        "relevant_resource": join_lines(asset.get("relevant_resource") or []),
        "relevant_to": join_lines(asset.get("relevant_to") or []),
        "research_area": join_lines(asset.get("research_area") or []),
        "scientific_domain": join_lines(asset.get("scientific_domain") or []),
        "asset_type": str(asset.get("type") or "storage"),
        "project_identifier": first_project(is_part_of),
        "platform": str(asset.get("platform") or ""),
        "platform_resource_identifier": str(asset.get("platform_resource_identifier") or ""),
        "status_info": str(asset.get("status_info") or ""),
        "aiod_entry_json": json_text(asset.get("aiod_entry"), {}),
        "api_version": "",
        "extra_json": "{}",
    }
