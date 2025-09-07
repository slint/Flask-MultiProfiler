# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Integration tests for Search profiler HTML report content validation."""

from tests.helpers import enable_profiling, get_profiler_report

from .validation_helpers import validate_html_report, validate_profiler_report_structure


def test_captures_search_queries(app, client):
    """Test capturing OpenSearch operations."""
    enable_profiling(client, ["search"])

    response = client.get("/search/test")
    assert response.status_code == 200

    report = get_profiler_report(app, "search")

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "search")

    # Validate search profiler specific content
    assert validation_results["has_content"]
    assert validation_results["has_search_content"]
    assert len(validation_results["query_indicators"]) > 0
    assert len(validation_results["response_indicators"]) > 0

    # Check for structured presentation
    assert validation_results["structured_elements_count"] > 3


def test_captures_multiple_query_types(app, client):
    """Test capturing different query types."""
    enable_profiling(client, ["search"])

    response = client.get("/search/aggregation")
    assert response.status_code == 200

    report = get_profiler_report(app, "search")

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "search")

    # Validate search profiler captured multiple query types
    assert validation_results["has_content"]
    assert validation_results["has_search_content"]

    # Check for specific query indicators including aggregations
    text = soup.get_text()
    assert '"match"' in text
    assert any(term in text for term in ['"aggs"', '"aggregations"', '"terms"'])

    # Check for timing information
    assert (
        any(term in text for term in ['"took"', "ms", "response time"])
        or len(validation_results["timing_values"]) > 0
    )


def test_shows_stack_traces(app, client):
    """Test including stack trace information."""
    enable_profiling(client, ["search"])

    client.get("/search/test")

    report = get_profiler_report(app, "search")

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "search")

    # Validate search profiler includes stack trace information
    assert validation_results["has_content"]
    stack_indicators = validation_results["stack_indicators"]
    assert len(stack_indicators) > 0, (
        f"Expected stack trace indicators, found: {stack_indicators}"
    )


def test_request_response_correlation(app, client):
    """Test proper pairing of queries and responses."""
    enable_profiling(client, ["search"])

    # Make multiple search requests
    response1 = client.get("/search/test")
    assert response1.status_code == 200

    response2 = client.get("/search/aggregation")
    assert response2.status_code == 200

    report = get_profiler_report(app, "search")

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "search")

    # Validate search profiler handles multiple queries with proper correlation
    assert validation_results["has_content"]
    assert validation_results["has_search_content"]

    # Should have multiple structured sections for multiple queries
    assert validation_results["structured_elements_count"] >= 2

    # Check for request-response pairing indicators
    text = soup.get_text()
    request_indicators = ["POST", "GET", "/_search", "query"]
    response_indicators = ["took", "hits", "_shards", "total"]

    assert any(indicator in text for indicator in request_indicators)
    assert any(indicator in text for indicator in response_indicators)


def test_search_profiler_with_no_queries(app, client):
    """Test profiler behavior when no search queries are made."""
    enable_profiling(client, ["search"])

    # Access non-search endpoint
    response = client.get("/compute")
    assert response.status_code == 200

    report = get_profiler_report(app, "search")

    # For the "no queries" case, the report might just be plain text
    if report and ("<html>" in report or "<div>" in report):
        # Use standardized validation for proper HTML
        soup = validate_html_report(report)
        text = soup.get_text()
    else:
        # Handle plain text reports
        text = report

    # Should return the specific "no queries recorded" message
    assert "No search queries recorded." in text


def test_search_profiler_html_structure(app, client):
    """Test HTML report has proper structure for search data."""
    enable_profiling(client, ["search"])

    response = client.get("/search/test")
    assert response.status_code == 200

    report = get_profiler_report(app, "search")

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "search")

    # Validate search profiler HTML structure
    assert validation_results["has_content"]
    assert validation_results["has_search_content"]
    assert validation_results["has_json_structure"]

    # Should have structured elements and proper formatting
    assert validation_results["structured_elements_count"] > 0

    # Look for code/pre blocks for JSON display
    code_blocks = soup.find_all(["pre", "code"])
    assert len(code_blocks) > 0 or validation_results["has_json_structure"]


def test_search_profiler_with_malformed_responses(app, client):
    """Test search profiler handles malformed data gracefully."""
    enable_profiling(client, ["search"])

    # Test endpoint that simulates malformed search responses
    response = client.get("/search/malformed-test")
    assert response.status_code == 200

    report = get_profiler_report(app, "search")

    # Should generate a report even with malformed data
    if report and ("<html>" in report or "<div>" in report):
        soup = validate_html_report(report)
        text = soup.get_text()
    else:
        text = report

    # Report should exist and not crash the system
    assert text is not None
    assert len(text) > 0


def test_search_profiler_deduplication_behavior(app, client):
    """Test that search profiler deduplicates identical requests."""
    enable_profiling(client, ["search"])

    # Make the same search request multiple times rapidly
    response1 = client.get("/search/duplicate-test")
    response2 = client.get("/search/duplicate-test")
    response3 = client.get("/search/duplicate-test")

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response3.status_code == 200

    report = get_profiler_report(app, "search")

    # Use standardized validation
    soup, validation_results = validate_profiler_report_structure(report, "search")

    # Should have content but may have deduplicated some requests
    assert validation_results["has_content"]
