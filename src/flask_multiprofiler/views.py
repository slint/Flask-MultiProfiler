# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from .models import ProfileSessions
from .proxies import current_multiprofiler

blueprint = Blueprint(
    "profiler",
    __name__,
    url_prefix="/profiler",
    template_folder="templates",
)


@blueprint.before_request
def check_permission():
    """Hook for permission check over all the profiler views."""
    permission_func = current_app.config["MULTIPROFILER_PERMISSION"]
    if not permission_func():
        abort(403)


@blueprint.context_processor
def add_active_session():
    """Make the active profiling session available to Jinja templates."""
    return {"active_session": current_multiprofiler.active_session}


def parse_form_bool(key: str) -> bool:
    """Parse boolean form flags with explicit false-like value support."""
    value = request.form.get(key)
    if value is None:
        return False

    normalized = str(value).strip().lower()
    return normalized not in {"", "0", "false", "off", "no"}


def group_requests_by_referrer(sess_requests: list) -> list[dict]:
    """Group request sessions by referrer path.

    Groups requests based on their referrer relationships, creating a hierarchy
    where requests with the same referrer are grouped together.
    """
    grouped_requests = []
    cur_group = None

    # We go in reverse order to finalize groups as soon as we find their parent.
    # This is important in cases where we have a mix of AJAX requests and normal
    # link navigation.
    for req in reversed(sess_requests):
        referrer = (
            urlparse(req.context.get("referrer")).path
            if req.context.get("referrer")
            else None
        )
        url = urlparse(req.context.get("url")).path

        # Start a new group if we don't have one
        if cur_group is None:
            cur_group = {"parent": None, "children": [], "referrer": referrer}

        # This is the parent of the current group
        if url == cur_group["referrer"]:
            cur_group["parent"] = req
            grouped_requests.insert(0, cur_group)
            cur_group = None
            continue

        # No referrer means this is a top-level request
        if referrer is None:
            # Finalize previous group if it has content
            if cur_group["children"]:
                cur_group["parent"] = cur_group["children"].pop(0)
                grouped_requests.insert(0, cur_group)
            elif cur_group["parent"] is not None:
                grouped_requests.insert(0, cur_group)

            # Insert new top-level request as its own group
            cur_group = {"parent": req, "children": [], "referrer": None}
            continue

        if referrer == cur_group["referrer"]:
            cur_group["children"].insert(0, req)
        else:
            # Changed referrer, finalize previous group
            if cur_group["children"]:
                cur_group["parent"] = cur_group["children"].pop(0)
                grouped_requests.insert(0, cur_group)
            elif cur_group["parent"] is not None:
                grouped_requests.insert(0, cur_group)
            # Start a new group with the current request
            cur_group = {"parent": None, "children": [req], "referrer": referrer}

    # Handle any remaining group
    if cur_group is not None:
        if cur_group["children"] and cur_group["parent"] is None:
            cur_group["parent"] = cur_group["children"].pop(0)
        if cur_group["parent"] is not None or cur_group["children"]:
            grouped_requests.insert(0, cur_group)

    return grouped_requests


@blueprint.get("/")
def index():
    """Index view."""
    sessions = ProfileSessions.get_all_sessions()

    grouped_sessions = {}
    for sess_id, sess_requests in sessions.items():
        grouped_sessions[sess_id] = group_requests_by_referrer(sess_requests)

    return render_template(
        "index.html",
        profiler_sessions=grouped_sessions,
    )


@blueprint.post("/start")
def start_session():
    """Start a profiling session."""
    active_session = current_multiprofiler.active_session
    if active_session:
        flash(
            f"You already have a profiling session running with {active_session['id']}",
            "error",
        )
    else:
        current_multiprofiler.active_session = {
            "id": secure_filename(request.form["id"]),
            "code": parse_form_bool("code"),
            "sql": parse_form_bool("sql"),
            "search": parse_form_bool("search"),
        }
    return redirect(url_for("profiler.index"), 303)


@blueprint.post("/stop")
def stop_session():
    """Stop a profiling session."""
    active_session = current_multiprofiler.active_session
    if not active_session:
        flash("You don't have an active profiling session running", "error")
    else:
        current_multiprofiler.active_session = None
    return redirect(url_for("profiler.index"), 303)


@blueprint.post("/delete")
def clear_sessions():
    """Clear profiling sessions from storage."""
    ProfileSessions.clear_sessions()
    return redirect(url_for("profiler.index"), 303)


@blueprint.get("/reports/<session_id>/<request_id>/<report_type>")
def report_view(session_id, request_id, report_type):
    """Serve an profiling HTML report."""
    content = ProfileSessions.get_request_report(session_id, request_id, report_type)
    if not content:
        abort(404)
    resp = make_response(content, 200)
    resp.content_type = "text/html"
    resp.charset = "utf-8"
    return resp
