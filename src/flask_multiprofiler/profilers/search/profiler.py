# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
import json
import logging
import re
import urllib.parse
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from flask import current_app

from ..base import BaseProfiler
from .renderer import SearchProfilerRenderer
from .stack_trace import StackFrameCapture


#
# Parsing utilities
#
class SearchQueryParser:
    """Parser for opensearch trace log entries."""

    # Regex patterns for different log entry types
    CURL_PATTERN = re.compile(
        r"curl\s+"
        r"(?P<headers>(?:-H\s+'[^']*'\s+)*)"
        r"(?P<method>-X\w+\s+)?"
        r"'(?P<url>[^']+)'\s*"
        r"(?:-d\s+'(?P<body>[^']*)')?"  # Note: simplified to work with single quotes
    )

    STATUS_PATTERN = re.compile(
        r"#\[(?P<status_code>\d+)\]\s+\((?P<duration>[\d.]+)s\)"
    )

    JSON_RESPONSE_PATTERN = re.compile(r"^#\{", re.MULTILINE)

    @classmethod
    def parse_curl_command(cls, message: str) -> Optional[Dict[str, Any]]:
        """Parse a curl command into structured request data."""
        match = cls.CURL_PATTERN.search(message)
        if not match:
            return None

        try:
            url = match.group("url")
            parsed_url = urllib.parse.urlparse(url)

            request_data = {
                "method": "GET",  # default
                "url": url,
                "scheme": parsed_url.scheme,
                "host": parsed_url.netloc,
                "path": parsed_url.path,
                "query_params": dict(urllib.parse.parse_qsl(parsed_url.query)),
                "headers": {},
                "body": None,
                "body_json": None,
            }

            # Parse method
            method_match = match.group("method")
            if method_match:
                request_data["method"] = method_match.strip("-X ").upper()

            # Parse headers
            headers_str = match.group("headers") or ""
            header_matches = re.findall(r"-H\s+'([^']*)'", headers_str)
            for header in header_matches:
                if ":" in header:
                    key, value = header.split(":", 1)
                    request_data["headers"][key.strip()] = value.strip()

            # Parse body
            body_str = match.group("body")
            if body_str:
                request_data["body"] = body_str
                try:
                    request_data["body_json"] = json.loads(body_str)
                except json.JSONDecodeError:
                    # Keep as string if not valid JSON
                    pass

            return request_data

        except Exception as e:
            current_app.logger.warning(f"Failed to parse curl command: {e}")
            return None

    @classmethod
    def parse_response(cls, message: str) -> Optional[Dict[str, Any]]:
        """Parse a combined status and response body."""
        response_data = {
            "status_code": None,
            "duration_seconds": None,
            "duration_ms": None,
            "body": None,
            "body_json": None,
            "parse_error": None,
        }

        # First, try to extract status line
        status_match = cls.STATUS_PATTERN.search(message)
        if status_match:
            try:
                response_data["status_code"] = int(status_match.group("status_code"))
                response_data["duration_seconds"] = float(
                    status_match.group("duration")
                )
                response_data["duration_ms"] = (
                    float(status_match.group("duration")) * 1000
                )
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Failed to parse status in response: {e}")

        # Now try to extract JSON body (everything after the status line)
        # Look for JSON starting with #{
        json_start = message.find("#{")
        if json_start != -1:
            json_part = message[json_start:]

            try:
                # Remove leading '#' from each line
                clean_json = "\n".join(
                    line[1:] if line.startswith("#") else line
                    for line in json_part.split("\n")
                )

                response_data["body"] = clean_json
                response_data["body_json"] = json.loads(clean_json)

            except json.JSONDecodeError as e:
                current_app.logger.warning(f"Failed to parse JSON response: {e}")
                response_data["body"] = json_part
                response_data["parse_error"] = str(e)
        elif response_data["status_code"]:
            # We have a status but no JSON body
            response_data["body"] = "(empty response)"

        # Return None if we didn't parse anything useful
        if not response_data["status_code"] and not response_data["body"]:
            return None

        return response_data

    @classmethod
    def identify_entry_type(cls, structured_record: Dict[str, Any]) -> str:
        """Identify the type of log entry."""
        message = structured_record["message"]
        level = structured_record.get("level", "")

        if cls.CURL_PATTERN.search(message):
            return "request"
        elif cls.STATUS_PATTERN.search(message) or level == "DEBUG":
            # Status and response are combined in the same message
            # DEBUG level messages are responses, and they often have status lines too
            return "response"
        else:
            return "unknown"

    @classmethod
    def parse_entry(cls, structured_record: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a structured record and add parsed data."""
        entry_type = cls.identify_entry_type(structured_record)
        message = structured_record["message"]

        parsed_record = structured_record.copy()
        parsed_record["entry_type"] = entry_type
        parsed_record["parsed_data"] = None

        if entry_type == "request":
            parsed_record["parsed_data"] = cls.parse_curl_command(message)
        elif entry_type == "response":
            parsed_record["parsed_data"] = cls.parse_response(message)

        return parsed_record


class SearchQueryCollector(logging.Handler):
    """A logging handler that collects OpenSearch/ElasticSearch queries."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queries = []
        self._seen_messages = set()  # Simple deduplication

    def emit(self, record):
        """Emit a record."""
        raw_message = record.getMessage()

        # Simple deduplication - skip if we've seen this exact message recently
        message_key = f"{record.name}:{raw_message}"
        if message_key in self._seen_messages:
            return

        # Keep only last 100 messages in dedup set to prevent memory growth
        if len(self._seen_messages) > 100:
            self._seen_messages.clear()
        self._seen_messages.add(message_key)

        structured_record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.fromtimestamp(record.created),
            "level": record.levelname,
            "logger_name": record.name,
            "thread_id": record.thread,
            "thread_name": record.threadName,
            "message": self.format(record),
            "raw_message": raw_message,
        }

        # Capture stack trace with locals (optimized for performance)
        stack_trace = StackFrameCapture.capture_stack_trace()

        if stack_trace:
            structured_record["stack_trace"] = stack_trace

        # Add process info
        structured_record["process_id"] = record.process
        if hasattr(record, "processName"):
            structured_record["process_name"] = record.processName

        # Parse the entry
        try:
            structured_record = SearchQueryParser.parse_entry(structured_record)
        except Exception as e:
            current_app.logger.warning(f"Failed to parse search query entry: {e}")
            # Continue with unparsed data

        self.queries.append(structured_record)


class SearchProfiler(BaseProfiler):
    """Profiler for search queries."""

    def __init__(self, logger_name):
        self.logger_name = logger_name
        self.collector = None
        self.logger = None
        self.original_level = None

    def start(self):
        """Start search query profiling."""
        self.logger = logging.getLogger(self.logger_name)
        self.original_level = self.logger.getEffectiveLevel()
        self.logger.setLevel(logging.DEBUG)

        self.collector = SearchQueryCollector()
        self.logger.addHandler(self.collector)

    def stop(self):
        """Stop search query profiling."""
        pass

    def collect_report(self) -> Optional[str]:
        """Collect search queries as HTML report."""
        if not self.collector or not self.collector.queries:
            return "<pre>No search queries recorded.</pre>"

        # Check if we have structured data (new format)
        if self.collector.queries:
            renderer = SearchProfilerRenderer()
            correlated_entries = renderer.correlate_entries(self.collector.queries)
            return renderer.render_report(correlated_entries)
        else:
            # Fallback to legacy format for backward compatibility
            return "<pre>" + "\n".join(self.collector.queries) + "</pre>"

    def cleanup(self):
        """Clean up logger handlers and restore original level."""
        if self.logger and self.collector:
            try:
                self.logger.removeHandler(self.collector)
            except Exception:
                current_app.logger.exception("Failed to remove search profiler handler")

        if self.logger and self.original_level is not None:
            try:
                self.logger.setLevel(self.original_level)
            except Exception:
                current_app.logger.exception("Failed to restore logger level")
