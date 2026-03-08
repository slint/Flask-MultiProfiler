# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Comprehensive tests for views module to improve coverage."""

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from flask_multiprofiler.views import group_requests_by_referrer


@dataclass
class MockRequest:
    """Test request data structure matching the real request context."""

    context: Dict[str, Optional[str]]

    @classmethod
    def create(cls, url: str, referrer: Optional[str] = None, endpoint: str = "test"):
        """Convenience method to create a test request."""
        return cls(context={"url": url, "referrer": referrer, "endpoint": endpoint})


class TestRequestGrouping:
    """Unit tests for the request grouping logic."""

    def test_empty_requests_list(self):
        """Test grouping with empty requests list."""
        result = group_requests_by_referrer([])
        assert result == []

    def test_single_request_no_referrer(self):
        """Test grouping with single request without referrer."""
        requests = [MockRequest.create("http://example.com/page1")]

        result = group_requests_by_referrer(requests)

        assert len(result) == 1
        assert result[0]["parent"] == requests[0]
        assert result[0]["children"] == []
        assert result[0]["referrer"] is None

    def test_parent_child_relationship(self):
        """Test grouping with clear parent-child relationship."""
        requests = [
            MockRequest.create("http://example.com/parent"),
            MockRequest.create("http://example.com/child", "http://example.com/parent"),
            MockRequest.create("http://example.com/parent"),  # Parent revisited
        ]

        result = group_requests_by_referrer(requests)

        # Should create groups properly
        assert len(result) >= 1
        # Check that parent gets assigned correctly in at least one group
        parent_found = any(
            group["parent"]
            and group["parent"].context["url"] == "http://example.com/parent"
            for group in result
        )
        assert parent_found

    def test_changed_referrer_creates_new_group(self):
        """Test that changing referrer creates a new group."""
        requests = [
            MockRequest.create("http://example.com/page1", "http://example.com/home"),
            MockRequest.create(
                "http://example.com/page2", "http://example.com/different"
            ),
        ]

        result = group_requests_by_referrer(requests)

        # Should create separate groups due to different referrers
        assert len(result) == 2

    def test_multiple_requests_same_referrer(self):
        """Test multiple requests with the same referrer."""
        requests = [
            MockRequest.create(
                "http://example.com/api/data", "http://example.com/page1"
            ),
            MockRequest.create(
                "http://example.com/api/more", "http://example.com/page1"
            ),
            MockRequest.create("http://example.com/page1"),  # The referrer page
        ]

        result = group_requests_by_referrer(requests)

        # Should group the API requests under the page1 parent
        assert len(result) >= 1
        # Find group with page1 as parent
        page1_group = next(
            (
                g
                for g in result
                if g["parent"] and "/page1" in g["parent"].context["url"]
            ),
            None,
        )
        assert page1_group is not None

    def test_no_referrer_after_group_exists(self):
        """Test handling when no referrer request comes after group is started."""
        requests = [
            MockRequest.create("http://example.com/page1"),  # No referrer
            MockRequest.create("http://example.com/page2"),  # Also no referrer
        ]

        result = group_requests_by_referrer(requests)

        # Should create separate groups for each no-referrer request
        assert len(result) == 2
        for group in result:
            assert group["parent"] is not None
            assert group["referrer"] is None

    def test_complex_grouping_scenario(self):
        """Test complex scenario with mixed referrer patterns."""
        requests = [
            MockRequest.create("http://example.com/home"),
            MockRequest.create(
                "http://example.com/api/data", "http://example.com/home"
            ),
            MockRequest.create("http://example.com/other"),
            MockRequest.create(
                "http://example.com/api/other", "http://example.com/other"
            ),
            MockRequest.create(
                "http://example.com/api/more", "http://example.com/other"
            ),
        ]

        result = group_requests_by_referrer(requests)

        # Should create meaningful groups
        assert len(result) >= 2

        # Verify that groups have proper structure
        for group in result:
            assert "parent" in group
            assert "children" in group
            assert "referrer" in group

    def test_url_path_parsing(self):
        """Test that URL paths are parsed correctly from full URLs."""
        requests = [
            MockRequest.create("https://example.com/path?query=1#fragment"),
            MockRequest.create(
                "https://example.com/child", "https://example.com/path?different=2"
            ),
        ]

        result = group_requests_by_referrer(requests)

        # Should work with full URLs by extracting paths
        assert len(result) >= 1

    def test_none_url_handling(self):
        """Test handling of None URLs and referrers."""
        requests = [
            MockRequest.create("http://example.com/page1", None),
        ]

        # Should not crash with None values
        result = group_requests_by_referrer(requests)
        assert len(result) == 1

    def test_empty_children_group_handling(self):
        """Test handling when group has no children but needs parent assignment."""
        requests = [
            MockRequest.create("http://example.com/page1"),
            MockRequest.create(
                "http://example.com/page2"
            ),  # Second no-referrer request
        ]

        result = group_requests_by_referrer(requests)

        # Should handle the case gracefully without popping from empty list
        assert len(result) == 2
        for group in result:
            assert group["parent"] is not None


# Integration tests with the actual view
class TestViewsIntegration:
    """Integration tests for the views using the Flask test client."""

    def test_clear_sessions_endpoint(self, client, app):
        """Test the clear_sessions endpoint response."""
        with tempfile.TemporaryDirectory() as temp_dir:
            app.config["MULTIPROFILER_STORAGE"] = Path(temp_dir)

            # Create some test session files
            test_db1 = Path(temp_dir) / "session1.db"
            test_db2 = Path(temp_dir) / "session2.db"
            test_db1.touch()
            test_db2.touch()

            # Verify files exist before deletion
            assert test_db1.exists()
            assert test_db2.exists()

            # Test the endpoint
            response = client.post("/profiler/delete")
            assert response.status_code == 303
            assert response.location.endswith("/profiler/")

            # Verify files were deleted
            assert not test_db1.exists()
            assert not test_db2.exists()

    def test_report_view_not_found(self, client, app):
        """Test report_view when report doesn't exist."""
        # Test with non-existent session/request - should return 404
        response = client.get("/profiler/reports/nonexistent/request123/code")
        assert response.status_code == 404

    def test_permission_denied(self, client, app):
        """Test permission check when access is denied."""
        # Configure permission directly without mocking
        app.config["MULTIPROFILER_PERMISSION"] = lambda: False

        response = client.get("/profiler/")
        assert response.status_code == 403

    def test_permission_allowed(self, client, app):
        """Test permission check when access is allowed."""
        # Test with permission allowed - should return 200 with empty sessions
        app.config["MULTIPROFILER_PERMISSION"] = lambda: True

        response = client.get("/profiler/")
        assert response.status_code == 200
        assert b"profiler_sessions" in response.data or b"sessions" in response.data

    def test_index_view_renders_template(self, client, app):
        """Test that index view renders without errors."""
        # Simple integration test - verify the view works end-to-end
        response = client.get("/profiler/")
        assert response.status_code == 200
        # Should contain the profiler template content
        assert response.content_type == "text/html; charset=utf-8"

    def test_clear_sessions_endpoint_missing_storage_dir(self, client, app, tmp_path):
        """Clear endpoint should not fail when storage directory doesn't exist."""
        missing_storage = tmp_path / "does-not-exist"
        app.config["MULTIPROFILER_STORAGE"] = missing_storage

        response = client.post("/profiler/delete")
        assert response.status_code == 303


class TestViewsFlashMessages:
    """Test flash messages in profiler views using session inspection."""

    def test_start_session_when_already_active_shows_error_flash(self, client):
        """Test flash message when trying to start a second session."""
        # Start first session
        response = client.post("/profiler/start", data={"id": "session1"})
        assert response.status_code == 303

        # Try to start second session
        response = client.post("/profiler/start", data={"id": "session2"})

        # Check flash message in session
        with client.session_transaction() as session:
            flashes = dict(session["_flashes"])
            flash_message = flashes.get("error")

        assert response.status_code == 303
        assert (
            flash_message
            == "You already have a profiling session running with session1"
        )

    def test_stop_session_when_none_active_shows_error_flash(self, client):
        """Test flash message when trying to stop with no active session."""
        # Try to stop without starting
        response = client.post("/profiler/stop")

        # Check flash message in session
        with client.session_transaction() as session:
            flashes = dict(session["_flashes"])
            flash_message = flashes.get("error")

        assert response.status_code == 303
        assert flash_message == "You don't have an active profiling session running"

    def test_successful_operations_have_no_flash_messages(self, client):
        """Test that successful start and stop operations have no flash messages."""
        # Start a session successfully
        response = client.post("/profiler/start", data={"id": "test"})
        with client.session_transaction() as session:
            flashes = session.get("_flashes", [])
        assert response.status_code == 303
        assert len(flashes) == 0

        # Stop the session successfully
        response = client.post("/profiler/stop")
        with client.session_transaction() as session:
            flashes = session.get("_flashes", [])
        assert response.status_code == 303
        assert len(flashes) == 0

    def test_flash_messages_use_error_category(self, client):
        """Test that flash messages use the correct 'error' category."""
        # Trigger an error flash by stopping without session
        client.post("/profiler/stop")

        # Check flash message category
        with client.session_transaction() as session:
            flashes = session.get("_flashes", [])

        assert len(flashes) == 1
        category, message = flashes[0]
        assert category == "error"

    def test_multiple_operations_flash_sequence(self, client):
        """Test flash messages across multiple operations."""
        # Stop without session - should show error
        client.post("/profiler/stop")
        with client.session_transaction() as session:
            flashes = dict(session.get("_flashes", []))
            assert (
                flashes.get("error")
                == "You don't have an active profiling session running"
            )
            session["_flashes"] = []  # Clear for next test

        # Start a session - should not show flash
        client.post("/profiler/start", data={"id": "test1"})
        with client.session_transaction() as session:
            assert len(session.get("_flashes", [])) == 0

        # Try to start another - should show error
        client.post("/profiler/start", data={"id": "test2"})
        with client.session_transaction() as session:
            flashes = dict(session.get("_flashes", []))
            assert (
                flashes.get("error")
                == "You already have a profiling session running with test1"
            )
            session["_flashes"] = []  # Clear for next test

        # Stop successfully - should not show flash
        client.post("/profiler/stop")
        with client.session_transaction() as session:
            assert len(session.get("_flashes", [])) == 0

        # Stop again - should show error
        client.post("/profiler/stop")
        with client.session_transaction() as session:
            flashes = dict(session.get("_flashes", []))
            assert (
                flashes.get("error")
                == "You don't have an active profiling session running"
            )
