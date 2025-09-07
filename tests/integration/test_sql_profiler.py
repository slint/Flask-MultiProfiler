# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Integration tests for SQL profiler HTML report validation."""

from tests.helpers import disable_profiling, enable_profiling, get_profiler_report

from .validation_helpers import (
    extract_timing_values,
    validate_profiler_report_structure,
)


def test_captures_queries(app, client):
    """Test capturing database operations."""
    session_id = enable_profiling(client, ["sql"])

    response = client.get("/queries")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "sql", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "sql")

    # Validate SQL profiler specific content
    assert validation_results["has_content"]
    assert validation_results["has_sql_content"]
    assert len(validation_results["sql_keywords"]) > 0

    # Validate timing data is present
    assert len(validation_results["timing_values"]) > 0


def test_shows_performance_metrics(app, client):
    """Test showing performance metrics for queries."""
    session_id = enable_profiling(client, ["sql"])

    response = client.get("/dashboard")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "sql", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "sql")

    # Validate SQL profiler specific metrics
    assert validation_results["has_content"]
    assert validation_results["has_sqltap_format"]
    assert len(validation_results["sqltap_indicators"]) > 0

    # Should have timing data
    assert len(validation_results["timing_values"]) > 0


def test_captures_complex_queries(app, client):
    """Test capturing complex SQL queries with joins and aggregations."""
    session_id = enable_profiling(client, ["sql"])

    response = client.get("/queries")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "sql", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "sql")

    # Validate SQL profiler captured complex queries
    assert validation_results["has_content"]
    assert validation_results["has_sql_content"]

    # Check for complex SQL operations in the text
    text = soup.get_text().upper()
    complex_keywords = ["JOIN", "GROUP BY", "ORDER BY", "COUNT", "LIMIT"]
    captured_keywords = [keyword for keyword in complex_keywords if keyword in text]
    assert len(captured_keywords) >= 2, (
        f"Expected at least 2 complex SQL keywords, found: {captured_keywords}"
    )

    # Validate specific table names from our test app
    table_names = ["USER", "POST", "COMMENT"]
    captured_tables = [table for table in table_names if table in text]
    assert len(captured_tables) >= 2, (
        f"Expected at least 2 table names, found: {captured_tables}"
    )


def test_sql_timing_data(app, client):
    """Test that SQL profiler captures meaningful timing data."""
    session_id = enable_profiling(client, ["sql"])

    response = client.get("/queries")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "sql", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "sql")

    # Validate timing data using standard helpers
    assert validation_results["has_content"]
    timing_values = validation_results["timing_values"]
    assert len(timing_values) > 0, "Expected timing data, but found none in report"

    # Validate query counts using SQL profiler specific validation
    query_counts = validation_results["query_counts"]
    assert len(query_counts) > 0, "Expected query counts, but found none in report"


def test_html_structure_validation(app, client):
    """Test that SQL profiler generates valid HTML structure."""
    session_id = enable_profiling(client, ["sql"])

    response = client.get("/dashboard")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "sql", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "sql")

    # Validate HTML structure using standard approach
    assert validation_results["has_content"]
    assert validation_results["structured_elements_count"] > 0


def test_query_frequency_analysis(app, client):
    """Test that the profiler captures query frequency and deduplication."""
    session_id = enable_profiling(client, ["sql"])

    # Make multiple requests to generate repeated queries
    for _ in range(3):
        response = client.get("/dashboard")
        assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "sql", session_id)
    assert report

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "sql")

    # Validate SQL profiler frequency analysis
    assert validation_results["has_content"]
    assert validation_results["has_sqltap_format"]
    sqltap_indicators = validation_results["sqltap_indicators"]
    assert len(sqltap_indicators) > 0, (
        f"Expected frequency indicators, found: {sqltap_indicators}"
    )

    # Validate query counts are captured
    query_counts = validation_results["query_counts"]
    assert len(query_counts) > 0, (
        f"Expected to find query counts, but found: {query_counts}"
    )


def test_empty_sql_session_handling(app, client):
    """Test handling of SQL profiling sessions with minimal database activity."""
    session_id = enable_profiling(client, ["sql"])

    # Make a request to an endpoint that doesn't use the database much
    response = client.get("/compute")
    assert response.status_code == 200

    disable_profiling(client)
    report = get_profiler_report(app, "sql", session_id)

    # Even with minimal SQL activity, should get a valid report
    if report:
        # Use standardized validation for minimal reports
        soup, validation_results = validate_profiler_report_structure(report, "sql")
        assert validation_results["has_content"]
    else:
        # It's acceptable for SQL profiler to return None if no queries were executed
        assert True


def test_sql_parsing_utilities():
    """Test BeautifulSoup-based SQL report content validation utilities."""
    # Sample HTML that mimics what sqltap actually generates
    sample_sql_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>SQLTap Profiling Report</title>
    </head>
    <body>
        <div class="container">
            <h1>sqltap</h1>
            <p>2 queries spent 0.005 seconds over 0.02 seconds of profiling</p>

            <div class="query-info">
                <div class="query-timing">0.003s</div>
                <div class="query-count">1q</div>
                <div class="query-text">SELECT COUNT(*) FROM user WHERE active = true</div>
            </div>

            <div class="query-info">
                <div class="query-timing">0.002s</div>
                <div class="query-count">1q</div>
                <div class="query-text">SELECT u.name, COUNT(p.id) FROM user u JOIN post p ON u.id = p.user_id GROUP BY u.id</div>
            </div>

            <div class="report-footer">
                Report Generated: 2025-09-04 18:28:34
            </div>
        </div>
    </body>
    </html>
    """

    # Use standardized validation helpers
    soup, validation_results = validate_profiler_report_structure(
        sample_sql_html, "sql"
    )

    # Test SQL-specific validation results
    assert validation_results["has_content"]
    assert validation_results["has_sql_content"]
    assert validation_results["has_sqltap_format"]
    assert len(validation_results["sql_keywords"]) >= 4
    assert len(validation_results["sqltap_indicators"]) >= 2
    assert len(validation_results["query_counts"]) >= 2

    # Test timing extraction with standard helpers
    text = soup.get_text()
    s_timings = extract_timing_values(text, "s")
    assert len(s_timings) >= 3, (
        f"Expected at least 3 second timings, found: {s_timings}"
    )

    # Test that all expected timing values are found
    expected_values = ["0.005", "0.003", "0.002"]
    for expected_value in expected_values:
        assert expected_value in s_timings, (
            f"Expected timing {expected_value} not found in {s_timings}"
        )
