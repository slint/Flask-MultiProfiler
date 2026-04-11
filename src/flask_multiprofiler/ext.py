# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, g, request, session

from .models import ProfileSessions
from .profilers import CodeProfiler, SearchProfiler, SQLProfiler
from .views import blueprint


class MultiProfiler:
    """Multi-profiler Flask extension."""

    def __init__(self, app=None):
        """Extension initialization."""
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Flask application initialization."""
        self.init_config(app)
        app.extensions["multiprofiler"] = self
        app.register_blueprint(blueprint)

        @app.before_request
        def _setup_profilers():
            """Clean expired sessions, set up and start profilers."""
            self.cleanup_expired_session()
            self.setup_request_profiling()

        @app.after_request
        def _refresh_session(response):
            """Refresh the active session expiration if there is one."""
            self.refresh_active_session()
            return response

        @app.teardown_request
        def _teardown_profilers(error):
            """Clean up profilers on teardown, especially important for errors."""
            self.teardown_request_profiling()

    def setup_request_profiling(self):
        """Set up profilers for the current request."""
        active_session = self.active_session
        if not active_session or not request.endpoint:
            return

        endpoint_ignored = any(
            re.match(e, request.endpoint)
            for e in current_app.config["MULTIPROFILER_IGNORED_ENDPOINTS"]
        )
        if endpoint_ignored:
            return

        g.profiler_session_id = active_session["id"]
        g.active_profilers = {}

        if active_session.get("code"):
            profiler = CodeProfiler()
            profiler.start()
            g.active_profilers["code"] = profiler

        if active_session.get("sql"):
            profiler = SQLProfiler()
            profiler.start()
            g.active_profilers["sql"] = profiler

        if active_session.get("search"):
            logger_name = current_app.config["MULTIPROFILER_SEARCH_TRACE_LOGGER"]
            profiler = SearchProfiler(logger_name)
            profiler.start()
            g.active_profilers["search"] = profiler

    def teardown_request_profiling(self):
        """Clean up profilers and store reports on request teardown."""
        reports = self.collect_reports()
        if reports:
            try:
                ProfileSessions.store_session_request(reports)
            except Exception:
                current_app.logger.exception("Failed to store profiler reports")

    def collect_reports(self):
        """Stop profilers and collect reports."""
        reports = {}

        if not hasattr(g, "active_profilers"):
            return reports

        for profiler_type, profiler in g.active_profilers.items():
            try:
                profiler.stop()
                report = profiler.collect_report()
                if report:
                    reports[profiler_type] = report
                profiler.cleanup()
            except Exception:
                current_app.logger.exception(
                    f"Failed to collect {profiler_type} profiler report"
                )

        return reports

    def init_config(self, app):
        """Initialize configuration."""
        app.config.setdefault(
            "MULTIPROFILER_STORAGE", Path(app.instance_path) / "profiler"
        )
        app.config.setdefault("MULTIPROFILER_SEARCH_TRACE_LOGGER", "opensearchpy.trace")
        app.config.setdefault(
            "MULTIPROFILER_ACTIVE_SESSION_LIFETIME", timedelta(minutes=60)
        )
        app.config.setdefault(
            "MULTIPROFILER_ACTIVE_SESSION_REFRESH", timedelta(minutes=30)
        )
        app.config.setdefault(
            "MULTIPROFILER_IGNORED_ENDPOINTS", ["static", r"profiler\..+"]
        )
        app.config.setdefault("MULTIPROFILER_PERMISSION", lambda: True)

        # Set default base template if not configured
        app.config.setdefault("MULTIPROFILER_BASE_TEMPLATE", "profiler/base.html")

    @property
    def active_session(self):
        """Get currently active profiling session, stored in ``Flask.session``."""
        return session.get("profiler_session")

    @active_session.setter
    def active_session(self, value):
        """Set currently active profiling session, stored in ``Flask.session``."""
        if value:
            value = dict(value)
            value["expires_at"] = (
                datetime.now(timezone.utc)
                + current_app.config["MULTIPROFILER_ACTIVE_SESSION_LIFETIME"]
            )
        session["profiler_session"] = value

    def cleanup_expired_session(self):
        """Remove expired profiling session from Flask session."""
        value = self.active_session
        if not value:
            return

        expires_at = (value or {}).get("expires_at")
        if not isinstance(expires_at, datetime):
            session.pop("profiler_session", None)
            return

        if expires_at < datetime.now(timezone.utc):
            session.pop("profiler_session", None)

    def refresh_active_session(self):
        """Refresh the expiration of the active session."""
        active_session = self.active_session
        if not active_session:
            return

        expires_at = active_session.get("expires_at")
        if not isinstance(expires_at, datetime):
            session.pop("profiler_session", None)
            return

        target_ts = (
            datetime.now(timezone.utc)
            + current_app.config["MULTIPROFILER_ACTIVE_SESSION_REFRESH"]
        )
        if target_ts > expires_at:
            refreshed_session = dict(active_session)
            refreshed_session["expires_at"] = (
                datetime.now(timezone.utc)
                + current_app.config["MULTIPROFILER_ACTIVE_SESSION_LIFETIME"]
            )
            self.active_session = refreshed_session
