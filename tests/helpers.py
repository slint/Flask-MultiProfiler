# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Test helper functions for Flask-MultiProfiler testing."""


def enable_profiling(client, profilers):
    """Enable profiling session with specified profilers."""
    import uuid

    session_id = str(uuid.uuid4())

    # Use the actual profiler API endpoint to start a session
    response = client.post(
        "/profiler/start",
        data={
            "id": session_id,
            "code": "code" in profilers,
            "sql": "sql" in profilers,
            "search": "search" in profilers,
        },
    )

    # Should redirect successfully
    assert response.status_code == 303

    return session_id


def disable_profiling(client):
    """Disable the current profiling session."""
    response = client.post("/profiler/stop")
    assert response.status_code == 303


def get_profiler_report(app, profiler_type, session_id=None):
    """Get HTML report for a specific profiler from the latest session."""
    from flask_multiprofiler.models import ProfileSessions

    # Get all sessions
    sessions = ProfileSessions.get_all_sessions()

    if not sessions:
        return None

    # Use provided session_id or get the latest session
    if session_id is None:
        session_id = list(sessions.keys())[0]

    if session_id not in sessions:
        return None

    session_entries = sessions[session_id]

    if not session_entries:
        return None

    # Get the latest request in the session
    latest_request = session_entries[0]
    request_id = latest_request.id

    # Get the report for the specific profiler type
    return ProfileSessions.get_request_report(session_id, request_id, profiler_type)
