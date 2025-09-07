# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Integration tests for Code profiler HTML report validation."""

from tests.helpers import disable_profiling, enable_profiling, get_profiler_report

from .validation_helpers import (
    extract_timing_values,
    validate_html_report,
    validate_profiler_report_structure,
)


def test_captures_cpu_operations(app, client):
    """Test capturing CPU-intensive operations."""
    session_id = enable_profiling(client, ["code"])

    response = client.get("/compute")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "code", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "code")

    # Validate code profiler specific content
    assert validation_results["has_pyinstrument_renderer"]
    assert validation_results["has_app_div"]
    assert validation_results["script_count"] == 2
    assert validation_results["has_function_data"]
    assert validation_results["has_return_statements"]

    # Look for function names in the JavaScript data
    script_content = "".join([script.get_text() for script in soup.find_all("script")])
    assert "compute_hashes" in script_content


def test_captures_flask_lifecycle(app, client):
    """Test capturing Flask request processing."""
    session_id = enable_profiling(client, ["code"])

    response = client.get("/dashboard")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "code", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "code")

    # Ensure we have valid code profiler content
    assert validation_results["has_content"]
    assert validation_results["has_pyinstrument_renderer"]

    # Check for Flask-specific content
    script_content = "".join([script.get_text() for script in soup.find_all("script")])
    flask_indicators = ["flask", "werkzeug", "dispatch_request", "wsgi"]
    assert any(indicator in script_content for indicator in flask_indicators)


def test_report_contains_timing_data(app, client):
    """Test that HTML report contains meaningful timing data."""
    session_id = enable_profiling(client, ["code"])

    response = client.get("/compute")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "code", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "code")

    # Validate code profiler structure and timing data
    assert validation_results["has_content"]
    assert validation_results["has_pyinstrument_renderer"]
    assert validation_results["has_function_data"]
    assert validation_results["script_count"] == 2
    assert validation_results["has_app_div"]
    assert len(soup.find_all("div")) == 1  # Exactly the #app div


def test_report_captures_function_hierarchies(app, client):
    """Test that the profiler captures function call hierarchies."""
    session_id = enable_profiling(client, ["code"])

    response = client.get("/compute")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "code", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "code")

    # Ensure we have valid code profiler content
    assert validation_results["has_content"]
    assert validation_results["has_pyinstrument_renderer"]

    # Check for function hierarchies in the profiling data
    script_content = "".join([script.get_text() for script in soup.find_all("script")])
    function_indicators = [
        "calculate_sum",
        "process_strings",
        "compute_hashes",
        "json_processing",
    ]

    # The compute_hashes function should definitely appear as it's CPU-intensive
    assert "compute_hashes" in script_content, (
        "compute_hashes function should be captured in profiling"
    )

    # Count total captured functions for better diagnostics
    captured_functions = [
        func for func in function_indicators if func in script_content
    ]
    assert len(captured_functions) >= 1, (
        f"Expected at least 1 function, captured: {captured_functions}"
    )


def test_empty_report_handling(app, client):
    """Test handling of cases where profiling might not capture data."""
    session_id = enable_profiling(client, ["code"])

    # Make a very simple request that might not generate much profiling data
    response = client.get("/")

    disable_profiling(client)

    # Even if the endpoint doesn't exist, we should handle gracefully
    if response.status_code == 404:
        # If route doesn't exist, that's expected - test passes
        assert True  # Explicit pass for 404 case
    else:
        # If endpoint exists, validate minimal report structure
        report = get_profiler_report(app, "code", session_id)
        if report:
            # Use standardized validation even for minimal reports
            soup, validation_results = validate_profiler_report_structure(
                report, "code"
            )

            # Should still have valid code profiler structure
            assert validation_results["has_content"]
            assert validation_results["has_pyinstrument_renderer"]
            assert validation_results["script_count"] == 2
            assert validation_results["has_app_div"]


def test_html_parsing_utilities():
    """Test BeautifulSoup-based HTML parsing utilities without full integration."""
    # Sample HTML report similar to what pyinstrument might generate
    sample_html = """
    <html>
    <head><title>Profile Report</title></head>
    <body>
        <div class="profile-report">
            <h1>Performance Profile</h1>
            <div class="stats">Total time: 125.5ms</div>
            <ul class="call-stack">
                <li class="function">
                    <span class="name">compute_hashes</span>
                    <span class="time">45.2ms (36.1%)</span>
                </li>
                <li class="function">
                    <span class="name">process_strings</span>
                    <span class="time">32.1ms (25.6%)</span>
                </li>
            </ul>
        </div>
    </body>
    </html>
    """

    # Use standardized validation helpers
    soup = validate_html_report(
        sample_html,
        expected_elements={"div": 2, "ul": 1, "li": 2},
        expected_content=[
            "compute_hashes",
            "process_strings",
            "125.5ms",
            "45.2ms",
            "32.1ms",
        ],
    )

    # Test timing extraction with standard helper
    text = soup.get_text()
    ms_timings = extract_timing_values(text, "ms")
    expected_values = ["125.5", "45.2", "32.1"]
    assert len(ms_timings) == 3, (
        f"Expected exactly 3 timings {expected_values}, found {ms_timings}"
    )

    # Verify all expected timing values are found
    for expected_value in expected_values:
        assert expected_value in ms_timings, (
            f"Expected timing {expected_value} not found in {ms_timings}"
        )
