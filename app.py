"""Flask entry point for the AIoD computational asset uploader."""

from __future__ import annotations

import json
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiod
from flask import Flask, jsonify, render_template, request

from aiod_helpers import (
    build_computational_asset_metadata,
    current_user,
    delete_computational_asset,
    describe_sdk_result,
    format_exception_for_ui,
    get_computational_asset,
    local_uploaded_assets_from_log,
    register_computational_asset,
    remove_local_uploaded_asset,
    safe_json,
    search_computational_assets,
    search_projects,
    verify_computational_asset_creation,
    write_transaction_log,
    submit_assets_for_review,
    append_submission_to_local_asset,
    retract_submission,
    mark_local_asset_retracted,
    list_submissions,
    current_rest_user,
    find_local_asset_identifier_by_submission,
    asset_to_form_values,
    update_computational_asset_via_rest,
    get_application_area_options,
    form_list_values,
    get_research_area_options,
    get_research_area_terms,
    get_industrial_sector_options,
    get_industrial_sector_terms,
    get_license_options,
    get_computational_asset_type_options,
    get_scientific_domain_options,
    get_scientific_domain_terms,
)

app = Flask(__name__)

AUTH_PROCESS = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "returncode": None,
    "output": [],
    "error": None,
}

AUTH_LOCK = threading.Lock()


@app.context_processor
def controlled_vocabulary_context() -> dict[str, Any]:
    """Expose controlled-vocabulary options to templates that need select fields."""
    return {
        "application_area_options": get_application_area_options(),
        "research_area_options": get_research_area_options(),
        "research_area_terms": get_research_area_terms(),
        "industrial_sector_options": get_industrial_sector_options(),
        "industrial_sector_terms": get_industrial_sector_terms(),
        "license_options": get_license_options(),
        "computational_asset_type_options": get_computational_asset_type_options(),
        "scientific_domain_options": get_scientific_domain_options(),
        "scientific_domain_terms": get_scientific_domain_terms(),
    }


class AuthOutputWriter:
    """File-like object used to stream SDK auth output to the Auth page."""

    def write(self, text: str) -> int:
        """Receive SDK output text and append non-empty lines to the shared buffer."""
        if not text:
            return 0

        # Preserve readable lines, but avoid adding empty fragments too aggressively.
        for line in text.splitlines():
            if line.strip():
                _append_auth_output(line)

        return len(text)

    def flush(self) -> None:
        """Satisfy the file-like interface expected by stdout/stderr redirection."""
        pass


def _append_auth_output(line: str) -> None:
    """Append one authentication output line to the shared process buffer."""
    with AUTH_LOCK:
        AUTH_PROCESS["output"].append(line.rstrip())


def _set_auth_process_state(
    *,
    running: bool | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    returncode: int | None = None,
    output: list[str] | None = None,
    error: str | None = None,
) -> None:
    """Update selected fields in the shared authentication process state."""
    with AUTH_LOCK:
        if running is not None:
            AUTH_PROCESS["running"] = running
        if started_at is not None:
            AUTH_PROCESS["started_at"] = started_at
        if finished_at is not None:
            AUTH_PROCESS["finished_at"] = finished_at
        if returncode is not None:
            AUTH_PROCESS["returncode"] = returncode
        if output is not None:
            AUTH_PROCESS["output"] = output
        if error is not None:
            AUTH_PROCESS["error"] = error


def _run_aiod_auth_subprocess() -> None:
    """Run the AIoD SDK authentication flow inside the Flask process.

    This streams the SDK output live to the Auth page, so the user can see
    the authentication URL/code while the SDK is waiting for approval.
    """
    with AUTH_LOCK:
        AUTH_PROCESS["running"] = True
        AUTH_PROCESS["started_at"] = datetime.now(timezone.utc).isoformat()
        AUTH_PROCESS["finished_at"] = None
        AUTH_PROCESS["returncode"] = None
        AUTH_PROCESS["output"] = []
        AUTH_PROCESS["error"] = None

    writer = AuthOutputWriter()

    try:
        token_path = Path.home() / ".aiod" / "token.toml"

        with redirect_stdout(writer), redirect_stderr(writer):
            print(f"AIoD token path: {token_path}", flush=True)

            if token_path.exists():
                print("Removing existing token.toml before authentication...", flush=True)
                token_path.unlink()
            else:
                print("No existing token.toml found.", flush=True)

            print("Starting AIoD authentication flow...", flush=True)

            # Runs in the same Python process as Flask, so the SDK state is updated.
            # Output is streamed live to AUTH_PROCESS["output"].
            aiod.create_token(write_to_file=True)

            print("Token flow completed. Verifying saved token...", flush=True)

            user = aiod.get_current_user()

            print(f"Authenticated as: {user}", flush=True)
            print("AIoD authentication completed and verified.", flush=True)

        with AUTH_LOCK:
            AUTH_PROCESS["returncode"] = 0
            AUTH_PROCESS["finished_at"] = datetime.now(timezone.utc).isoformat()
            AUTH_PROCESS["running"] = False
            AUTH_PROCESS["error"] = None

    except Exception as exc:
        with AUTH_LOCK:
            AUTH_PROCESS["error"] = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
            AUTH_PROCESS["returncode"] = 1
            AUTH_PROCESS["finished_at"] = datetime.now(timezone.utc).isoformat()
            AUTH_PROCESS["running"] = False


def start_aiod_auth_flow() -> bool:
    """Start auth flow if not already running.

    Returns True if a new auth process was started.
    """
    with AUTH_LOCK:
        if AUTH_PROCESS["running"]:
            return False

    thread = threading.Thread(target=_run_aiod_auth_subprocess, daemon=True)
    thread.start()
    return True


def get_auth_process_snapshot() -> dict[str, Any]:
    """Return a thread-safe copy of the current authentication process state."""
    with AUTH_LOCK:
        return {
            "running": AUTH_PROCESS["running"],
            "started_at": AUTH_PROCESS["started_at"],
            "finished_at": AUTH_PROCESS["finished_at"],
            "returncode": AUTH_PROCESS["returncode"],
            "output": list(AUTH_PROCESS["output"]),
            "error": AUTH_PROCESS["error"],
        }


def form_defaults() -> dict[str, Any]:
    """Return the default values used to initialize the asset metadata form."""
    return {
        "name": "",
        "date_published": "",
        "same_as": "",
        "is_accessible_for_free": "on",
        "asset_version": "",
        "alternate_name": "",
        "application_area": "",
        "description": "",
        "description_plain": "",
        "description_html": "",
        "industrial_sector": "",
        "keyword": "",
        "license": "",
        "relevant_link": "",
        "research_area": "",
        "scientific_domain": "",
        "asset_type": "storage",
        "project_identifier": "",
        "platform": "",
        "platform_resource_identifier": "",
        "status_info": "",
        "api_version": "",
        "extra_json": "{}",
        "citation": "",
        "contact": "",
        "creator": "",
        "distribution_json": "[]",
        "has_part": "",
        "is_part_of": "",
        "media_json": "[]",
        "note_json": "[]",
        "relevant_resource": "",
        "relevant_to": "",
        "aiod_entry_json": "{}",
    }


@app.route("/", methods=["GET", "POST"])
def index():
    """Render and process the computational asset registration form."""
    message = None
    error = None
    preview = None
    result = None
    identifier = None
    verification = None
    form = form_defaults()

    if request.method == "POST":
        form.update(request.form.to_dict())
        form["description"] = form.get("description_plain", "")
        form["application_area"] = "\n".join(form_list_values(request.form, "application_area"))
        form["industrial_sector"] = "\n".join(form_list_values(request.form, "industrial_sector"))
        form["research_area"] = "\n".join(form_list_values(request.form, "research_area"))
        form["scientific_domain"] = "\n".join(form_list_values(request.form, "scientific_domain"))
        action = request.form.get("action")

        try:
            metadata = build_computational_asset_metadata(request.form)
            preview = safe_json(metadata)

            if action == "submit":
                raw_result = register_computational_asset(metadata, request.form.get("api_version"))
                result = describe_sdk_result(raw_result)

                # If the SDK returns a requests.Response with HTTP error,
                # do not treat it as success.
                http_status = result.get("http_status_code")

                if http_status and int(http_status) >= 400:
                    verification = {
                        "confirmed": False,
                        "confidence": "high",
                        "identifier": "",
                        "reason": (
                            f"AIoD rejected the payload with HTTP {http_status}. "
                            "See the SDK response details to identify the invalid field."
                        ),
                        "checks": [],
                    }

                    write_transaction_log(metadata, raw_result, result, verification)
                    message = f"Registration failed: AIoD returned HTTP {http_status}."

                else:
                    verification = verify_computational_asset_creation(
                        metadata,
                        raw_result,
                        request.form.get("api_version"),
                    )

                    identifier = verification.get("identifier") or result.get("identifier")
                    write_transaction_log(metadata, raw_result, result, verification)

                    if verification.get("confirmed"):
                        if identifier:
                            with open("last_computational_asset_identifier.txt", "w", encoding="utf-8") as f:
                                f.write(identifier)

                        message = (
                            "Registration confirmed. "
                            f"Identifier: {identifier or 'not available'}"
                        )
                    else:
                        message = (
                            "Registration not confirmed: the SDK did not return a verifiable identifier "
                            "and the post-submit lookup did not find a reliable match."
                        )

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"

    return render_template(
        "index.html",
        form=form,
        preview=preview,
        result=result,
        identifier=identifier,
        verification=verification,
        verification_json=safe_json(verification),
        result_json=safe_json(result),
        message=message,
        error=error,
    )


def build_auth_context(auth_message: str | None = None) -> dict[str, Any]:
    """Build the template context for the authentication status panel."""
    sdk_ok, sdk_info = current_user()
    rest_ok, rest_info = current_rest_user()

    # Consider the app fully authenticated only if both checks pass.
    ok = sdk_ok and rest_ok

    info = {
        "sdk": {
            "ok": sdk_ok,
            "info": sdk_info,
        },
        "rest": {
            "ok": rest_ok,
            "info": rest_info,
        },
    }

    return {
        "ok": ok,
        "info": info,
        "auth_process": get_auth_process_snapshot(),
        "auth_message": auth_message,
    }


def handle_auth_action() -> str | None:
    """Apply a posted authentication action and return a UI message."""
    auth_message = None

    action = request.form.get("action")

    if action == "start_auth":
        started = start_aiod_auth_flow()
        if started:
            auth_message = "Authentication flow started. Follow the link/code shown below."
        else:
            auth_message = "Authentication flow is already running."

    elif action == "clear_auth_output":
        with AUTH_LOCK:
            AUTH_PROCESS["output"] = []
            AUTH_PROCESS["error"] = None
            AUTH_PROCESS["returncode"] = None
            AUTH_PROCESS["started_at"] = None
            AUTH_PROCESS["finished_at"] = None
            AUTH_PROCESS["running"] = False

        auth_message = "Authentication output cleared."

    return auth_message


@app.route("/auth", methods=["GET", "POST"])
def auth():
    """Render the authentication status page and handle auth actions."""
    auth_message = None

    if request.method == "POST":
        auth_message = handle_auth_action()

    return render_template("auth.html", **build_auth_context(auth_message))


@app.route("/auth/modal", methods=["GET", "POST"])
def auth_modal():
    """Render the authentication status panel for the in-page modal."""
    auth_message = None

    if request.method == "POST":
        auth_message = handle_auth_action()

    return render_template("partials/auth_panel.html", **build_auth_context(auth_message))


@app.route("/projects", methods=["GET", "POST"])
def projects():
    """Search AIoD projects and show candidate identifiers for asset metadata."""
    data = None
    error = None
    query = ""
    version = ""
    limit = 50

    if request.method == "POST":
        query = request.form.get("query", "")
        version = request.form.get("version", "")

        try:
            limit = int(request.form.get("limit", "50") or 50)
        except ValueError:
            limit = 50

        try:
            data = search_projects(query=query, version=version, limit=limit)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"

    return render_template(
        "projects.html",
        query=query,
        version=version,
        limit=limit,
        data=data,
        error=error,
    )


@app.route("/asset", methods=["GET", "POST"])
def asset():
    """Read or delete one AIoD computational asset by identifier."""
    asset_data = None
    delete_result = None
    delete_result_json = None
    local_delete_result = None
    local_delete_result_json = None
    error = None
    readable_error = None
    identifier = ""
    version = ""
    action = "read"

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        version = request.form.get("version", "").strip()
        action = request.form.get("action", "read")

        try:
            if action == "delete":
                try:
                    raw_delete_result = delete_computational_asset(identifier, version)
                    delete_result = describe_sdk_result(raw_delete_result)
                    delete_result["remote_delete_status"] = "requested"
                    delete_result["remote_delete_message"] = "Delete request sent to AIoD."

                except KeyError as exc:
                    # Common case: the asset is already missing remotely.
                    # In that case we still clean the local log, because the local card is stale.
                    delete_result = {
                        "python_type": f"{type(exc).__module__}.{type(exc).__name__}",
                        "identifier": identifier,
                        "remote_delete_status": "not_found",
                        "remote_delete_message": str(exc),
                        "note": (
                            "AIoD reports that the asset was not found. "
                            "The local history entry will still be removed."
                        ),
                    }

                local_delete_result = remove_local_uploaded_asset(identifier)
                local_delete_result_json = safe_json(local_delete_result)
                delete_result_json = safe_json(delete_result)

            else:
                asset_data = get_computational_asset(identifier, version)

        except Exception as exc:
            readable_error = format_exception_for_ui(exc)
            error = safe_json(readable_error)

    return render_template(
        "asset.html",
        identifier=identifier,
        version=version,
        action=action,
        asset_data=asset_data,
        asset_json=safe_json(asset_data),
        delete_result=delete_result,
        delete_result_json=delete_result_json,
        local_delete_result=local_delete_result,
        local_delete_result_json=local_delete_result_json,
        error=error,
        readable_error=readable_error,
    )


@app.route("/computational-assets", methods=["GET", "POST"])
def computational_assets():
    """Search visible computational assets in the AIoD catalogue."""
    data = None
    error = None
    query = ""
    version = ""
    limit = 50

    if request.method == "POST":
        query = request.form.get("query", "")
        version = request.form.get("version", "")

        try:
            limit = int(request.form.get("limit", "50") or 50)
        except ValueError:
            limit = 50

        try:
            data = search_computational_assets(query=query, version=version, limit=limit)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"

    return render_template(
        "computational_assets.html",
        query=query,
        version=version,
        limit=limit,
        data=data,
        error=error,
    )

@app.route("/local-assets", methods=["GET", "POST"])
def local_assets():
    """Show locally logged uploads and process submit, retract, and delete actions."""
    message = None
    error = None
    readable_error = None
    operation_result = None
    operation_result_json = None

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        identifier = request.form.get("identifier", "").strip()

        try:
            if action == "delete":
                try:
                    raw_delete_result = delete_computational_asset(identifier, "")
                    delete_result = describe_sdk_result(raw_delete_result)
                    delete_result["remote_delete_status"] = "requested"
                    delete_result["remote_delete_message"] = "Delete request sent to AIoD."
                except KeyError as exc:
                    delete_result = {
                        "python_type": f"{type(exc).__module__}.{type(exc).__name__}",
                        "identifier": identifier,
                        "remote_delete_status": "not_found",
                        "remote_delete_message": str(exc),
                        "note": (
                            "AIoD reports that the asset was not found. "
                            "The local history entry will still be removed."
                        ),
                    }

                local_delete_result = remove_local_uploaded_asset(identifier)

                operation_result = {
                    "remote_delete": delete_result,
                    "local_cleanup": local_delete_result,
                }
                operation_result_json = safe_json(operation_result)

                message = (
                    f"Asset {identifier} deleted from AIoD/local history, "
                    "or removed locally if it was already missing remotely."
                )

            elif action == "submit":
                comment = request.form.get("comment", "").strip()

                submission_result = submit_assets_for_review(
                    asset_identifiers=[identifier],
                    comment=comment or "Submitting computational asset for review.",
                )

                local_update = append_submission_to_local_asset(
                    asset_identifier=identifier,
                    submission_result=submission_result,
                )

                operation_result = {
                    "submission": submission_result,
                    "local_update": local_update,
                }
                operation_result_json = safe_json(operation_result)

                submission_json = submission_result.get("http_json") or {}
                submission_identifier = (
                    submission_json.get("submission_identifier")
                    or submission_json.get("identifier")
                    or "not available"
                )

                message = (
                    f"Asset {identifier} submitted for review. "
                    f"Submission identifier: {submission_identifier}."
                )

            elif action == "retract":
                submission_identifier = request.form.get("submission_identifier", "").strip()

                retract_result = retract_submission(submission_identifier)

                # Retracts triggered from /submissions may not include an asset identifier.
                # Recover it from the local log through the submission identifier when possible.
                if not identifier:
                    identifier = find_local_asset_identifier_by_submission(submission_identifier)

                if identifier:
                    local_update = mark_local_asset_retracted(
                        asset_identifier=identifier,
                        retract_result=retract_result,
                    )
                else:
                    local_update = {
                        "updated": 0,
                        "message": (
                            "Remote retract completed, but no local asset identifier was found "
                            "for this submission. Local uploads could not be updated."
                        ),
                    }

                operation_result = {
                    "retract": retract_result,
                    "local_update": local_update,
                }
                operation_result_json = safe_json(operation_result)

                message = (
                    f"Submission {submission_identifier} retracted. "
                    f"Local update: {local_update.get('message')}"
                )

        except Exception as exc:
            readable_error = format_exception_for_ui(exc)
            error = safe_json(readable_error)

    data = local_uploaded_assets_from_log()

    return render_template(
        "local_assets.html",
        data=data,
        message=message,
        error=error,
        readable_error=readable_error,
        operation_result=operation_result,
        operation_result_json=operation_result_json,
    )

@app.route("/submissions", methods=["GET"])
def submissions():
    """List review submissions visible to the authenticated AIoD account."""
    data = None
    error = None
    readable_error = None

    try:
        data = list_submissions()
    except Exception as exc:
        readable_error = format_exception_for_ui(exc)
        error = safe_json(readable_error)

    return render_template(
        "submissions.html",
        data=data,
        error=error,
        readable_error=readable_error,
    )

@app.route("/asset-edit-data", methods=["GET"])
def asset_edit_data():
    """Return asset metadata converted into edit-form values for the modal."""
    identifier = request.args.get("identifier", "").strip()
    version = request.args.get("version", "").strip()

    try:
        if not identifier:
            raise ValueError("Asset identifier is required.")

        asset_data = get_computational_asset(identifier, version)

        if not isinstance(asset_data, dict):
            raise ValueError("The retrieved asset is not a JSON object.")

        return jsonify({
            "ok": True,
            "identifier": identifier,
            "form": asset_to_form_values(asset_data),
            "asset": asset_data,
        })

    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": format_exception_for_ui(exc),
        }), 400

@app.route("/asset-update", methods=["POST"])
def asset_update():
    """Update an existing computational asset and return the refreshed metadata."""
    try:
        identifier = request.form.get("identifier", "").strip()
        version = request.form.get("api_version", "").strip()

        if not identifier:
            raise ValueError("Asset identifier is required.")

        metadata = build_computational_asset_metadata(request.form)

        update_result = update_computational_asset_via_rest(
            identifier=identifier,
            metadata=metadata,
        )

        updated_asset = get_computational_asset(identifier, version)

        return jsonify({
            "ok": True,
            "message": f"Asset {identifier} updated successfully.",
            "identifier": identifier,
            "update_result": update_result,
            "asset": updated_asset,
        })

    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": format_exception_for_ui(exc),
        }), 400

if __name__ == "__main__":
    app.run(debug=True)
