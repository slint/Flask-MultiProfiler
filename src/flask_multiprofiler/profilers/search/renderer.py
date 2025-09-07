# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
import json
from pathlib import Path
from typing import Any, Dict, List

import jinja2


class SearchProfilerRenderer:
    """Renderer for search profiler HTML reports using Jinja templates."""

    def __init__(self):
        self.templates_dir = Path(__file__).parent / "templates"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.templates_dir),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        # Add custom filters
        self.env.filters["json_pretty"] = self._json_pretty_filter

    def _json_pretty_filter(self, value, indent: int = 2) -> str:
        """Jinja filter to format JSON with pretty printing."""
        if value is None:
            return ""
        try:
            return json.dumps(value, indent=indent)
        except (TypeError, ValueError):
            return str(value)

    def render_report(self, correlated_entries: List[Dict[str, Any]]) -> str:
        """Render the complete search queries report."""
        if not correlated_entries:
            return "<pre>No search queries recorded.</pre>"

        # Calculate total query time
        total_time = 0
        for entry in correlated_entries:
            if entry.get("type") == "query" and entry.get("response"):
                parsed_data = entry["response"].get("parsed_data", {})
                if parsed_data and parsed_data.get("duration_ms"):
                    total_time += parsed_data["duration_ms"]

        template = self.env.get_template("report.html")
        return template.render(entries=correlated_entries, total_time=total_time)

    def correlate_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Correlate request-response pairs sequentially."""
        correlated = []
        pending_request = None

        for entry in entries:
            entry_type = entry.get("entry_type", "unknown")

            if entry_type == "request":
                if pending_request:
                    # Orphaned request - previous request had no response
                    correlated.append(
                        {
                            "type": "orphaned_request",
                            "request": pending_request,
                        }
                    )
                pending_request = entry
            elif entry_type == "response" and pending_request:
                # Normal query - request with matching response
                correlated.append(
                    {
                        "type": "query",
                        "request": pending_request,
                        "response": entry,
                    }
                )
                pending_request = None
            elif entry_type == "response":
                # Orphaned response - response without a preceding request
                correlated.append({"type": "orphaned_response", "response": entry})
            else:
                # Unparsed entry
                correlated.append({"type": "unparsed", "entry": entry})

        # Handle any remaining pending request
        if pending_request:
            correlated.append(
                {
                    "type": "orphaned_request",
                    "request": pending_request,
                }
            )

        return correlated
