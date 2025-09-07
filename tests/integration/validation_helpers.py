# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Standard validation helpers for profiler HTML report testing."""

import re

from bs4 import BeautifulSoup


def validate_html_report(report, expected_elements=None, expected_content=None):
    """Standard HTML report validation returning BeautifulSoup object."""
    soup = BeautifulSoup(report, "html.parser")

    # Basic structure validation
    assert soup.find("html") is not None or soup.find("div") is not None, (
        "Missing basic HTML structure"
    )

    # Expected elements validation
    if expected_elements:
        for element, count in expected_elements.items():
            found = soup.find_all(element)
            assert len(found) == count, (
                f"Expected {count} {element} elements, found {len(found)}"
            )

    # Expected content validation
    if expected_content:
        text = soup.get_text()
        for content in expected_content:
            assert content in text, f"Expected content '{content}' not found in report"

    return soup


def extract_timing_values(text, unit="ms"):
    """Extract timing values for specified unit from text."""
    patterns = {
        "ms": r"(\d+(?:\.\d+)?)\s*ms",
        "s": r"(\d+(?:\.\d+)?)\s*s(?:ec)?",
        "μs": r"(\d+(?:\.\d+)?)\s*μs",
    }

    if unit not in patterns:
        raise ValueError(
            f"Unsupported time unit: {unit}. Use one of: {list(patterns.keys())}"
        )

    return re.findall(patterns[unit], text)


def extract_all_timing_values(text):
    """Extract all timing values as (value, unit) tuples."""
    all_timings = []

    # Pattern that captures value and unit together
    pattern = r"(\d+(?:\.\d+)?)\s*(ms|μs|s|sec)"
    matches = re.findall(pattern, text)

    for value, unit in matches:
        # Normalize unit names
        normalized_unit = "s" if unit == "sec" else unit
        all_timings.append((float(value), normalized_unit))

    return all_timings


def validate_code_profiler_content(soup):
    """Validate pyinstrument-specific report content."""
    script_content = "".join([script.get_text() for script in soup.find_all("script")])

    results = {
        "has_pyinstrument_renderer": "pyinstrumentHTMLRenderer" in script_content,
        "has_app_div": soup.find("div", {"id": "app"}) is not None,
        "script_count": len(soup.find_all("script")),
        "has_function_data": "function()" in script_content,
        "has_return_statements": "return" in script_content,
    }

    return results


def validate_sql_profiler_content(soup):
    """Validate sqltap-specific report content."""
    text = soup.get_text()

    # SQL keyword detection
    sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE", "JOIN"]
    found_keywords = [kw for kw in sql_keywords if kw in text.upper()]

    # Sqltap-specific patterns
    sqltap_indicators = ["queries spent", "seconds of profiling", "sqltap"]
    found_indicators = [ind for ind in sqltap_indicators if ind in text.lower()]

    # Query count patterns (format: 1q, 2q, etc.)
    query_counts = re.findall(r"\d+q\b", text)

    results = {
        "sql_keywords": found_keywords,
        "sqltap_indicators": found_indicators,
        "query_counts": query_counts,
        "has_sql_content": len(found_keywords) > 0,
        "has_sqltap_format": len(found_indicators) > 0,
    }

    return results


def validate_search_profiler_content(soup):
    """Validate search profiler-specific report content."""
    text = soup.get_text()

    # Search query indicators
    query_indicators = [
        '"query"',
        '"match"',
        '"bool"',
        '"terms"',
        '"aggs"',
        '"aggregations"',
    ]
    found_query_indicators = [ind for ind in query_indicators if ind in text]

    # Response indicators
    response_indicators = ['"hits"', '"total"', '"_source"', '"took"', '"_shards"']
    found_response_indicators = [ind for ind in response_indicators if ind in text]

    # Stack trace indicators
    stack_indicators = ["traceback", "stack trace", "line", "file"]
    found_stack_indicators = [
        ind for ind in stack_indicators if ind.lower() in text.lower()
    ]

    # Check for JSON structure
    has_json = "{" in text and "}" in text

    results = {
        "query_indicators": found_query_indicators,
        "response_indicators": found_response_indicators,
        "stack_indicators": found_stack_indicators,
        "has_json_structure": has_json,
        "has_search_content": len(found_query_indicators) > 0
        or len(found_response_indicators) > 0,
    }

    return results


def validate_profiler_report_structure(report, profiler_type):
    """Universal report validation returning soup and profiler-specific results."""
    soup = validate_html_report(report)

    validation_functions = {
        "code": validate_code_profiler_content,
        "sql": validate_sql_profiler_content,
        "search": validate_search_profiler_content,
    }

    if profiler_type not in validation_functions:
        raise ValueError(f"Unsupported profiler type: {profiler_type}")

    specific_results = validation_functions[profiler_type](soup)

    # Common validations for all profilers
    text = soup.get_text()

    # For code profilers, content is mainly in JavaScript, so check for that
    if profiler_type == "code":
        script_content = "".join(
            [script.get_text() for script in soup.find_all("script")]
        )
        has_content = len(script_content.strip()) > 0
    else:
        has_content = len(text.strip()) > 0

    common_results = {
        "has_content": has_content,
        "timing_values": extract_all_timing_values(text),
        "structured_elements_count": len(
            soup.find_all(["table", "div", "ul", "ol", "section", "article"])
        ),
    }

    return soup, {**common_results, **specific_results}
