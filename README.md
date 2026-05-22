# AIoD Computational Asset Uploader Tool

A Flask-based web application for preparing, validating, registering, reviewing, editing, and deleting AIoD `computational_asset` metadata through the official `aiondemand` Python SDK and selected AIoD REST API endpoints.

This repository is intended to make the AIoD integration flow transparent for technical partners. The code separates the web layer from the AIoD integration layer so reviewers can quickly understand where the SDK is used, where REST calls are used, and how local upload history is maintained.

## Table Of Contents

- [Purpose](#purpose)
- [Feature Overview](#feature-overview)
- [Technical Architecture](#technical-architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running The Application](#running-the-application)
- [Authentication](#authentication)
- [Application Pages](#application-pages)
- [AIoD SDK And REST API Usage](#aiod-sdk-and-rest-api-usage)
- [Post-Submit Verification](#post-submit-verification)
- [Payload Structure](#payload-structure)
- [Local Files](#local-files)
- [Security Notes](#security-notes)
- [Troubleshooting](#troubleshooting)

## Purpose

The application submits metadata to AIoD. It does not upload the physical software package, source code, model artifact, dataset, or documentation file.

The actual computational asset should remain hosted on a stable external source, for example:

- GitHub
- Zenodo
- An institutional repository
- A product or project website

The app helps users prepare an AIoD-compatible metadata payload, register it, verify whether registration succeeded, and manage review-related operations.

## Feature Overview

- AIoD authentication from the **Auth check** modal, with `/auth` kept as a direct fallback page.
- Professional metadata form for creating a new `computational_asset`.
- Date picker for `date_published`.
- Searchable single-select controls for AIoD-controlled `license` and computational asset `type` vocabularies.
- JSON payload preview before registration.
- Asset registration through the official `aiondemand` SDK.
- Post-submit verification through `get_asset()` and catalogue fallback checks.
- Project identifier lookup for the `is_part_of` metadata field.
- Asset read, edit, delete, submit-for-review, and retract workflows.
- **Catalogue assets** page for visible AIoD catalogue entries.
- **Local uploads** page based on locally recorded app activity.
- Local transaction log in `aiod_upload_transactions.jsonl`.

## Technical Architecture

The project is organized around a small Flask application and a dedicated AIoD helper module.

| File | Responsibility |
| --- | --- |
| `app.py` | Flask routes, request handling, authentication flow orchestration, and template rendering. |
| `aiod_helpers.py` | AIoD SDK calls, REST API calls, metadata payload construction, token handling, verification logic, and local transaction-log helpers. |
| `auth.py` | Minimal command-line helper for creating and validating an AIoD SDK token. |
| `templates/` | HTML templates for the web interface. |
| `static/` | CSS and JavaScript assets used by the web interface. |
| `requirements.txt` | Python dependencies required by the application. |

High-level flow:

```text
Browser -> Flask routes in app.py -> AIoD helpers in aiod_helpers.py -> AIoD SDK / REST APIs
```

Local upload history is stored separately in:

```text
aiod_upload_transactions.jsonl
```

That file is only a local application log. It is not an AIoD source of truth.

## Requirements

- Python 3.10+
- AIoD account enabled for SDK/API usage
- Access to the `aiondemand` Python package

## Installation

From PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Optional pip upgrade:

```powershell
python -m pip install --upgrade pip
```

## Running The Application

Start the Flask app:

```powershell
python app.py
```

Open the application:

```text
http://127.0.0.1:5000
```

Quick start:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Before registering assets, complete authentication from the **Auth check** link in the top navigation.

The same authentication view is also available directly at:

```text
http://127.0.0.1:5000/auth
```

## Authentication

Authentication can be handled directly from the web application.

Open **Auth check** from the top navigation. It opens an in-page modal so the current page remains in place.

The direct fallback page is:

```text
http://127.0.0.1:5000/auth
```

Then:

1. Click **Start authentication**.
2. Wait for the authentication-flow panel to generate the login link.
3. Open the generated authentication link.
4. Sign in to AIoD.
5. Confirm the authorization request.
6. Return to the app.
7. Verify that the status is **Authenticated**.

The SDK stores the local token at:

```text
C:\Users\<user>\.aiod\token.toml
```

If the token expires or becomes invalid, open **Auth check** and start authentication again. The app removes the previous token before starting a new authentication flow.

The modal shows three concise checks:

- Overall authentication readiness.
- SDK token status.
- REST API token status.

When **Start authentication** is clicked, the flow panel displays a loading animation until the SDK output and authentication link are available.

## Application Pages

### Asset Form

The main page creates a new `computational_asset` metadata payload.

Key fields include:

- Name
- Description
- Same as
- Project identifier
- Date published
- Version
- Type, loaded from `https://api.aiodp.eu/computational_asset_types`
- License, loaded from `https://api.aiodp.eu/licenses`
- Keywords
- Alternate names
- Application areas
- Industrial sectors
- Research areas
- Scientific domains
- Relevant links
- Platform
- Platform resource identifier
- Status information URL
- Extra JSON

The **Project identifier** field is sent as:

```json
"is_part_of": ["PROJECT_IDENTIFIER"]
```

### Projects

Searches for AIoD Project identifiers.

The implementation tries:

```python
aiod.projects.search(..., asset_type="projects")
```

and also:

```python
aiod.projects.get_list(...)
```

with pagination and local filtering.

Draft projects may not appear in search results. If the project identifier is already known, paste it directly into the main asset form.

### Read / Delete Asset

Reads or deletes an asset by identifier.

Read uses:

```python
aiod.computational_assets.get_asset(identifier=...)
```

Delete uses:

```python
aiod.computational_assets.delete(identifier=...)
```

When deleting an asset, the app:

1. Attempts to delete the asset from AIoD.
2. Removes the matching local-history entry if AIoD confirms deletion.
3. Also removes the local entry if AIoD reports that the asset no longer exists.

### Catalogue Assets

Searches visible computational assets in the AIoD catalogue by calling:

```python
aiod.computational_assets.get_list(...)
```

The page applies local filtering to the SDK results.

This is not equivalent to **My Assets** in the AIoD editor. It only shows entries returned as visible through the SDK/API catalogue.

### Local Uploads

Shows assets created through this local application instance.

Data is read from:

```text
aiod_upload_transactions.jsonl
```

Each card includes the asset name, main URL, identifier, creation timestamp, version, linked project, confirmation status, and operational buttons.

This page does not query all assets owned by the AIoD account. It only displays the local transaction history produced by this app.

### Submissions

Lists AIoD review submissions visible to the authenticated account and supports retracting submissions where the REST API allows it.

### Auth Check

Checks SDK and REST authentication status from a modal opened by the top navigation.

The modal keeps the user on the current page and shows:

- Three compact readiness checks.
- **Start authentication** and **Clear output** actions.
- Authentication-flow output and the generated login link.

The direct `/auth` page uses the same status panel and remains available as a fallback.

## AIoD SDK And REST API Usage

The project intentionally keeps AIoD integration code centralized in `aiod_helpers.py`, while `app.py` remains responsible for Flask routes, request handling, and rendering templates.

### SDK Integration

The official `aiondemand` SDK is imported as:

```python
import aiod
```

Main SDK usage points:

| Function | SDK usage | Purpose |
| --- | --- | --- |
| `current_user()` | `aiod.get_current_user()` | Verifies SDK authentication. |
| `search_projects()` | `aiod.projects.search(...)`, `aiod.projects.get_list(...)` | Finds Project identifiers. |
| `register_computational_asset()` | `aiod.computational_assets.register(...)` | Registers a computational asset. |
| `get_computational_asset()` | `aiod.computational_assets.get_asset(...)` | Retrieves one asset by identifier. |
| `delete_computational_asset()` | `aiod.computational_assets.delete(...)` | Deletes one asset. |
| `list_computational_assets()` | `aiod.computational_assets.get_list(...)` | Lists visible catalogue assets. |
| `aiod_rest_base_url()` | `aiod.config.api_server` | Builds REST URLs from active SDK configuration. |

Authentication is started in `app.py` through:

```python
aiod.create_token(write_to_file=True)
```

The same authentication flow is validated with:

```python
aiod.get_current_user()
```

### REST Integration

Some workflows are implemented with direct REST calls through:

```python
import requests
```

These workflows are handled explicitly at HTTP level because they involve token refresh, submissions, retractions, or metadata updates.

| Function | REST request | Purpose |
| --- | --- | --- |
| `refresh_aiod_access_token()` | `POST` to the OpenID Connect token endpoint | Refreshes the access token from `~/.aiod/token.toml`. |
| `current_rest_user()` | `GET /submissions` | Verifies access to REST-protected endpoints. |
| `submit_assets_for_review()` | `POST /submissions` | Submits assets for AIoD review. |
| `list_submissions()` | `GET /submissions` | Lists review submissions. |
| `retract_submission()` | `POST /submissions/retract/{submission_identifier}` | Retracts a review submission. |
| `update_computational_asset_via_rest()` | `PUT /computational_assets/{identifier}` | Updates asset metadata. |

All REST requests use `aiod_rest_headers()`, which builds the `Authorization: Bearer ...` header from a freshly refreshed token when possible.

### Controlled Vocabulary Integration

Several form fields are populated from AIoD REST vocabulary endpoints and cached in `aiod_helpers.py`.

| Function | Endpoint | Used by |
| --- | --- | --- |
| `get_application_area_options()` | `https://api.aiodp.eu/application_areas` | Application areas multi-select. |
| `get_license_options()` | `https://api.aiodp.eu/licenses` | License searchable single-select. |
| `get_computational_asset_type_options()` | `https://api.aiodp.eu/computational_asset_types` | Computational asset type searchable single-select. |
| `get_research_area_terms()` | `https://api.aiodp.eu/research_areas` | Research areas multi-select and reference modal. |
| `get_industrial_sector_terms()` | `https://api.aiodp.eu/industrial_sectors` | Industrial sectors multi-select and reference modal. |
| `get_scientific_domain_terms()` | `https://api.aiodp.eu/scientific_domains` | Scientific domains multi-select and reference modal. |

If a vocabulary endpoint cannot be loaded, the relevant select shows a disabled fallback option instead of hardcoded values.

### Integration Flow Summary

The SDK is used for the core computational asset catalogue lifecycle:

```text
register -> verify/read -> list/search -> delete
```

REST APIs are used for workflows that need explicit HTTP handling:

```text
refresh token -> submit for review -> list submissions -> retract submission -> update asset metadata
```

## Post-Submit Verification

After **Register on AIoD**, the app tries to confirm creation in two ways.

First, if the SDK returns an `identifier`, the app calls:

```python
aiod.computational_assets.get_asset(identifier)
```

Second, if no identifier is returned, the app searches for a compatible asset through:

```python
aiod.computational_assets.get_list(...)
```

The fallback match checks:

- `name`
- `same_as`
- `is_part_of`

If verification is **Not confirmed**, avoid repeatedly submitting the same payload. That can create duplicates that are not immediately visible. Use a unique name or check **Catalogue assets** / **Read asset** first.

## Payload Structure

Simplified example:

```json
{
  "name": "Secure Data Processing Service",
  "date_published": "2026-05-13T00:00:00.000",
  "same_as": "https://example.org/resources/secure-data-processing-service",
  "is_accessible_for_free": true,
  "version": "1.0.0",
  "description": {
    "plain": "A computational asset for secure data processing workflows.",
    "html": ""
  },
  "is_part_of": ["proj_..."],
  "keyword": ["data processing", "secure infrastructure"],
  "license": "apache-2.0",
  "relevant_link": ["https://example.org/documentation"],
  "type": "docker container"
}
```

The date picker returns:

```text
YYYY-MM-DD
```

The app converts it to:

```text
YYYY-MM-DDT00:00:00.000
```

### Extra JSON

The **Extra JSON** field adds metadata fields that are not exposed directly in the form.

Example:

```json
{
  "custom_field": "custom value"
}
```

The value must be a valid JSON object. Extra fields are merged into the final payload and can override existing fields. Use this only when the required AIoD schema field is known.

## Local Files

### `aiod_upload_transactions.jsonl`

Local transaction log for assets registered through this app.

Each line is an independent JSON object containing:

- UTC timestamp
- Submitted metadata payload
- SDK response summary
- Verification result
- Asset identifier, when available
- Submission metadata, when an asset is submitted for review

If this file is deleted:

- The app keeps working.
- **Local uploads** becomes empty.
- The file is recreated on the next registration.
- Existing AIoD assets are not deleted.

### `last_computational_asset_identifier.txt`

Optional helper file created when registration returns an identifier. It stores the latest created identifier for quick manual testing.

## Security Notes

Do not store or submit sensitive data in the form, repository, logs, or screenshots.

Avoid committing:

- Passwords
- Tokens
- API keys
- Real `.env` files
- Credentials
- Private configuration
- Personal data
- Sensitive data
- Logs containing confidential information

The AIoD token is stored at:

```text
C:\Users\<user>\.aiod\token.toml
```

Never commit that folder or file.

## Troubleshooting

### `Refresh token is not valid`

The local token is expired or corrupted. Open **Auth check**, click **Start authentication**, and retry after the new token is created.

### `Response [400]`

The payload does not satisfy the AIoD schema. Check **SDK response detail**. The app exposes the real HTTP response body, including field-level validation details when AIoD returns them.

Common causes:

- Invalid URL
- Missing required field
- Unsupported `type` value. Use the AIoD-controlled **Computational asset type** select.
- Invalid date format
- Invalid project identifier in `is_part_of`
- Non-compliant Extra JSON fields

### Asset Created But Missing From Local Uploads

**Local uploads** only shows assets registered through this app and saved in:

```text
aiod_upload_transactions.jsonl
```

Assets created from Swagger, the AIoD editor, an external script, or another machine do not appear there.

### Asset Deleted From AIoD But Still Visible Locally

The local card is stale. Use **Delete** from the card, or remove the corresponding line from:

```text
aiod_upload_transactions.jsonl
```
