# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
from datetime import datetime, timedelta, timezone

from flask import Flask

from flask_multiprofiler import MultiProfiler


class TestMultiProfilerExtension:
    """Test MultiProfiler extension initialization and basic functionality."""

    def test_extension_initialization_with_app(self, app):
        """Test extension initialization with app passed to constructor."""
        # The app fixture already has MultiProfiler initialized
        assert "multiprofiler" in app.extensions
        assert isinstance(app.extensions["multiprofiler"], MultiProfiler)

    def test_extension_initialization_factory_pattern(self):
        """Test extension initialization using factory pattern."""
        test_app = Flask(__name__)
        profiler = MultiProfiler()
        profiler.init_app(test_app)

        assert "multiprofiler" in test_app.extensions
        assert test_app.extensions["multiprofiler"] is profiler

    def test_blueprint_registration(self, app):
        """Test that the profiler blueprint is registered."""
        # The app fixture already has MultiProfiler initialized
        assert "profiler" in app.blueprints

    def test_default_config_values(self, app):
        """Test that default configuration values are set correctly."""
        # The app fixture already has MultiProfiler initialized
        assert "MULTIPROFILER_STORAGE" in app.config
        assert "MULTIPROFILER_SEARCH_TRACE_LOGGER" in app.config
        assert "MULTIPROFILER_ACTIVE_SESSION_LIFETIME" in app.config
        assert "MULTIPROFILER_ACTIVE_SESSION_REFRESH" in app.config
        assert "MULTIPROFILER_IGNORED_ENDPOINTS" in app.config
        assert "MULTIPROFILER_PERMISSION" in app.config
        assert "MULTIPROFILER_BASE_TEMPLATE" in app.config

        # Test default values
        assert app.config["MULTIPROFILER_SEARCH_TRACE_LOGGER"] == "opensearchpy.trace"
        assert "static" in app.config["MULTIPROFILER_IGNORED_ENDPOINTS"]
        assert callable(app.config["MULTIPROFILER_PERMISSION"])
        assert app.config["MULTIPROFILER_BASE_TEMPLATE"] == "profiler/base.html"

    def test_custom_config_values(self):
        """Test that custom configuration values are preserved."""
        # Create a minimal app for this specific test
        test_app = Flask(__name__)
        test_app.config["MULTIPROFILER_SEARCH_TRACE_LOGGER"] = "custom.logger"
        test_app.config["MULTIPROFILER_IGNORED_ENDPOINTS"] = ["custom.endpoint"]

        MultiProfiler(test_app)

        assert test_app.config["MULTIPROFILER_SEARCH_TRACE_LOGGER"] == "custom.logger"
        assert test_app.config["MULTIPROFILER_IGNORED_ENDPOINTS"] == ["custom.endpoint"]

    def test_profiler_routes_exist(self, app, client):
        """Test that profiler routes are accessible."""
        # The app fixture already has MultiProfiler initialized
        # Test index route - should return 200 using default base template
        response = client.get("/profiler/")
        assert response.status_code == 200
        assert b"<title>Profiler</title>" in response.data

    def test_active_session_property_empty(self, app):
        """Test active_session property when no session is set."""
        profiler = app.extensions["multiprofiler"]

        with app.test_request_context():
            assert profiler.active_session is None

    def test_hooks_are_registered(self, app):
        """Test that Flask hooks are properly registered."""
        # The app fixture already has MultiProfiler initialized
        # Check that before_request, after_request, and teardown_request hooks exist
        assert len(app.before_request_funcs[None]) >= 1
        assert len(app.after_request_funcs[None]) >= 1
        assert len(app.teardown_request_funcs[None]) >= 1

    def test_session_expiration_behavior(self, app, client):
        """Test real session expiration behavior."""
        with client.session_transaction() as session:
            # Create expired session
            expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
            session["profiler_session"] = {
                "id": "test_session",
                "expires_at": expired_time,
            }

        # Make request - should clean up expired session
        response = client.get("/profiler/")
        assert response.status_code == 200

        # Verify session was cleaned up
        with client.session_transaction() as session:
            assert "profiler_session" not in session

    def test_session_refresh_behavior(self, app, client):
        """Test session refresh on activity."""
        # Start a profiling session
        response = client.post("/profiler/start", data={"id": "test_session"})
        assert response.status_code == 303

        # Get initial expiration time
        with client.session_transaction() as session:
            initial_expires = session["profiler_session"]["expires_at"]

        # Make another request (simulating user activity)
        response = client.get("/profiler/")
        assert response.status_code == 200

        # Session should still exist (not expired)
        with client.session_transaction() as session:
            assert "profiler_session" in session
            # Expiration may be refreshed if within refresh window
            new_expires = session["profiler_session"]["expires_at"]
            assert new_expires >= initial_expires

    def test_ignored_endpoints_behavior(self, app, client):
        """Test that ignored endpoints don't trigger profiling."""
        # Start profiling session
        response = client.post(
            "/profiler/start", data={"id": "test_session", "code": "on"}
        )
        assert response.status_code == 303

        # Access static endpoint (should be ignored)
        # Note: This would typically be handled by Flask's static file serving
        # but we can test the profiler blueprint endpoints are ignored
        response = client.get("/profiler/")
        assert response.status_code == 200
        # The profiler index page should load normally without profiling itself

    def test_profiler_storage_configuration(self, app, client):
        """Test profiler works with custom storage configuration."""
        # The app fixture already has custom storage configured via temp_storage

        # Start profiling session
        response = client.post(
            "/profiler/start", data={"id": "test_session", "code": "on"}
        )
        assert response.status_code == 303

        # Make a request that would be profiled
        # This tests the storage system works with custom directory
        response = client.get("/dashboard")  # Use an endpoint that exists
        assert response.status_code == 200

        # Clear sessions should work
        response = client.post("/profiler/delete")
        assert response.status_code == 303

    def test_permission_function_behavior(self, app, client):
        """Test permission function controls access."""
        # Set permission function that denies access
        app.config["MULTIPROFILER_PERMISSION"] = lambda: False

        response = client.get("/profiler/")
        assert response.status_code == 403

        # Change to allow access
        app.config["MULTIPROFILER_PERMISSION"] = lambda: True

        response = client.get("/profiler/")
        assert response.status_code == 200

    def test_session_refresh_persists_to_client_cookie(self, tmp_path):
        """Session expiration must be extended when refresh condition is met."""
        test_app = Flask(__name__)
        test_app.config["SECRET_KEY"] = "test-secret-key"
        test_app.config["MULTIPROFILER_STORAGE"] = tmp_path / "profiler"
        test_app.config["MULTIPROFILER_ACTIVE_SESSION_LIFETIME"] = timedelta(minutes=60)
        test_app.config["MULTIPROFILER_ACTIVE_SESSION_REFRESH"] = timedelta(minutes=120)

        MultiProfiler(test_app)

        @test_app.get("/ping")
        def ping():
            return {"ok": True}

        client = test_app.test_client()
        old_expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        with client.session_transaction() as session:
            session["profiler_session"] = {
                "id": "refresh-check",
                "expires_at": old_expiry,
            }

        response = client.get("/ping")
        assert response.status_code == 200

        with client.session_transaction() as session:
            updated_expiry = session["profiler_session"]["expires_at"]

        assert updated_expiry > old_expiry

    def test_missing_expires_at_in_session_does_not_crash_request(self, tmp_path):
        """Malformed session payload without expires_at must not break request lifecycle."""
        test_app = Flask(__name__)
        test_app.config["SECRET_KEY"] = "test-secret-key"
        test_app.config["MULTIPROFILER_STORAGE"] = tmp_path / "profiler"
        MultiProfiler(test_app)

        @test_app.get("/ping")
        def ping():
            return {"ok": True}

        client = test_app.test_client()
        with client.session_transaction() as session:
            session["profiler_session"] = {"id": "broken-session"}

        response = client.get("/ping")
        assert response.status_code == 200

        with client.session_transaction() as session:
            assert "profiler_session" not in session

    def test_dashboard_timestamp_is_utc_aware(self, client):
        """Test app timestamps should include explicit UTC offset."""
        response = client.get("/dashboard")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["timestamp"].endswith("+00:00")
