# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
import linecache
import re
from types import FrameType
from typing import Any, Dict, Optional, Set


class StackFrameCapture:
    """Capture, filter and serialize stack frame information including locals."""

    # Define frame exclusion patterns - (filename_pattern, function_names_to_exclude)
    EXCLUDE_FRAME_PATTERNS = [
        # Python internals
        ("/logging/__init__.py", None),  # None means exclude all functions in this file
        ("/http/server.py", None),
        ("/socketserver.py", None),
        ("/threading.py", None),
        # Profiler itself
        ("profiler.py", ["emit"]),
        ("stack_trace.py", ["capture_stack_traces"]),  # Exclude our own capture logic
        # OpenSearch internals - filter all frames from these modules
        ("opensearchpy/", None),
        ("opensearch_dsl/", None),
        # Flask/Werkzeug WSGI
        (
            "flask/app.py",
            ["wsgi_app", "__call__", "full_dispatch_request", "dispatch_request"],
        ),
        (
            "werkzeug/",
            ["__call__", "debug_application", "execute", "run_wsgi", "handle"],
        ),
    ]

    # Limits for stack trace capture
    MAX_FRAMES = 20
    MAX_FRAMES_WITH_LOCALS = 5

    # Limits for locals extraction (reduced for better performance)
    MAX_LOCALS_VALUE_LENGTH = 500
    MAX_LOCALS_COLLECTION_ITEMS = 10
    MAX_LOCALS_STRING_LENGTH = 100
    MAX_LOCALS_SERIALIZATION_DEPTH = 3
    MAX_LOCALS_PER_FRAME = 20

    # Variables to exclude from locals capture (exact matches)
    SKIPPED_VARIABLE_NAMES = [
        "self",
        "cls",
        "frame",
        "sys",
        "traceback",
        "logging",
        "current_app",
        "request",
        "g",
        "session",
    ]

    # Patterns for variables to exclude from locals capture
    EXCLUDE_VARIABLE_PATTERNS = [
        r"^__.*",  # Dunder variables
        r"^_.*",  # Private variables
        # Generate exact match pattern from variable names
        r"^(" + "|".join(SKIPPED_VARIABLE_NAMES) + r")$",
    ]

    @classmethod
    def capture_stack_trace(
        cls,
        max_frames: Optional[int] = None,
        max_locals_frames: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        """Capture current stack trace with filtering and locals extraction."""
        import sys

        # Use class attributes as defaults
        if max_frames is None:
            max_frames = cls.MAX_FRAMES
        if max_locals_frames is None:
            max_locals_frames = cls.MAX_FRAMES_WITH_LOCALS

        stack_trace = []
        try:
            frame = sys._getframe(1)  # Skip this method's frame
            relevant_frames_captured = 0

            while frame and len(stack_trace) < max_frames:
                if not cls.should_skip_frame(frame):
                    # Only capture locals for the first few relevant frames to reduce overhead
                    include_locals = relevant_frames_captured < max_locals_frames

                    frame_info = cls.extract_frame_info(
                        frame,
                        include_locals=include_locals,
                    )
                    stack_trace.append(frame_info)
                    relevant_frames_captured += 1
                frame = frame.f_back

        except Exception:
            # If capture fails, return empty list
            return []

        return stack_trace

    @classmethod
    def should_skip_frame(cls, frame: FrameType) -> bool:
        """Check if a frame object should be skipped based on filter patterns."""
        filename = frame.f_code.co_filename
        function_name = frame.f_code.co_name

        for filename_pattern, function_names in cls.EXCLUDE_FRAME_PATTERNS:
            if filename_pattern in filename:
                if function_names is None or function_name in function_names:
                    return True
        return False

    @classmethod
    def extract_frame_info(
        cls, frame: FrameType, include_locals: bool = True, include_source: bool = True
    ) -> Dict[str, Any]:
        """Extract comprehensive frame information safely."""
        frame_info = {
            "filename": frame.f_code.co_filename,
            "lineno": frame.f_lineno,
            "function": frame.f_code.co_name,
            "module": frame.f_globals.get("__name__", "<unknown>"),
        }

        if include_source:
            frame_info["source_context"] = cls._get_source_context(
                frame.f_code.co_filename, frame.f_lineno
            )

        if include_locals:
            frame_info["locals"] = cls._extract_locals(frame)

        return frame_info

    @classmethod
    def _extract_locals(cls, frame: FrameType) -> Dict[str, Any]:
        """Safely extract and serialize local variables."""
        locals_dict = {}

        for name, value in list(frame.f_locals.items())[: cls.MAX_LOCALS_PER_FRAME]:
            if cls._should_skip_variable(name):
                continue

            locals_dict[name] = cls._serialize_value(value, depth=0, seen=set())

        return locals_dict

    @classmethod
    def _should_skip_variable(cls, name: str) -> bool:
        """Check if a variable should be skipped based on patterns."""
        for pattern in cls.EXCLUDE_VARIABLE_PATTERNS:
            if re.match(pattern, name):
                return True
        return False

    @classmethod
    def _get_simple_preview(cls, obj: Any) -> str:
        """Get a simple string preview of an object for display."""
        if obj is None:
            return "None"
        elif isinstance(obj, bool):
            return str(obj)
        elif isinstance(obj, (int, float)):
            return str(obj)
        elif isinstance(obj, str):
            if len(obj) > 20:
                return f'"{obj[:17]}..."'
            return f'"{obj}"'
        else:
            try:
                repr_str = repr(obj)
                if len(repr_str) > 30:
                    return f"{type(obj).__name__}(...)"
                return repr_str
            except Exception:
                return f"{type(obj).__name__}"

    @classmethod
    def _serialize_value(cls, obj: Any, depth: int, seen: Set[int]) -> Dict[str, Any]:
        """Serialize a value to simple, template-safe representation."""
        indent = "  " * depth
        obj_id = id(obj)
        if obj_id in seen or depth > cls.MAX_LOCALS_SERIALIZATION_DEPTH:
            return {
                "type": type(obj).__name__,
                "display": "...",
                "truncated": True,
            }
        seen.add(obj_id)

        try:
            obj_type = type(obj).__name__
            obj_module = type(obj).__module__

            # Handle None
            if obj is None:
                return {"type": "NoneType", "display": "None"}

            # Handle primitives - pass through as-is
            if isinstance(obj, (bool, int, float)):
                return {"type": obj_type, "display": str(obj)}

            # Handle strings with truncation
            if isinstance(obj, str):
                if len(obj) > cls.MAX_LOCALS_STRING_LENGTH:
                    return {
                        "type": "str",
                        "display": f'"{obj[: cls.MAX_LOCALS_STRING_LENGTH]}..." ({len(obj)} chars)',
                        "truncated": True,
                    }
                return {"type": "str", "display": f'"{obj}"'}

            # Handle lists and tuples - convert to simple display string early
            if isinstance(obj, (list, tuple)):
                try:
                    length = len(obj)
                    if length == 0:
                        return {"type": obj_type, "display": f"{obj_type}([])"}

                    # Show first few items with proper depth tracking
                    preview_items = []
                    for item in obj[: cls.MAX_LOCALS_COLLECTION_ITEMS]:
                        item_data = cls._serialize_value(item, depth + 1, seen)
                        preview_items.append(item_data["display"])

                    if length > cls.MAX_LOCALS_COLLECTION_ITEMS:
                        items_str = ", ".join(preview_items) + f", ... ({length} total)"
                    else:
                        items_str = ", ".join(preview_items)

                    # Pretty-print for better readability
                    if length <= 3 and depth < 2:  # Short lists, keep inline
                        display = f"{obj_type}([{items_str}])"
                    else:  # Longer lists or deeper nesting, use newlines
                        items_formatted = []
                        for item in preview_items:
                            items_formatted.append(f"\n{indent}  {item}")
                        if length > cls.MAX_LOCALS_COLLECTION_ITEMS:
                            items_formatted.append(f"\n{indent}  ... ({length} total)")
                        items_str = ",".join(items_formatted)
                        display = f"{obj_type}([{items_str}\n{indent}])"

                    return {
                        "type": obj_type,
                        "display": display,
                        "length": length,
                    }

                except Exception:
                    return {
                        "type": obj_type,
                        "display": f"{obj_type}(<error accessing elements>)",
                    }

            # Handle dicts - convert to simple display string early
            if isinstance(obj, dict):
                try:
                    length = len(obj)
                    if length == 0:
                        return {"type": "dict", "display": "dict({})"}

                    # Show first few key-value pairs with proper depth tracking
                    preview_pairs = []
                    for k, v in list(obj.items())[: cls.MAX_LOCALS_COLLECTION_ITEMS]:
                        key_data = cls._serialize_value(k, depth + 1, seen)
                        val_data = cls._serialize_value(v, depth + 1, seen)
                        preview_pairs.append(
                            f"{key_data['display']}: {val_data['display']}"
                        )

                    if length > cls.MAX_LOCALS_COLLECTION_ITEMS:
                        pairs_str = ", ".join(preview_pairs) + f", ... ({length} total)"
                    else:
                        pairs_str = ", ".join(preview_pairs)

                    # Pretty-print for better readability
                    if length <= 3 and depth < 2:  # Short dicts, keep inline
                        display = f"dict({{{pairs_str}}})"
                    else:  # Longer dicts or deeper nesting, use newlines
                        pairs_formatted = []
                        for pair in preview_pairs:
                            pairs_formatted.append(f"\n{indent}  {pair}")
                        if length > cls.MAX_LOCALS_COLLECTION_ITEMS:
                            pairs_formatted.append(f"\n{indent}  ... ({length} total)")
                        pairs_str = ",".join(pairs_formatted)
                        display = f"dict({{{pairs_str}\n{indent}}})"

                    return {
                        "type": "dict",
                        "display": display,
                        "length": length,
                    }

                except Exception:
                    return {"type": "dict", "display": "dict(<error accessing items>)"}

            # Handle all other objects with simple string representation
            try:
                # Try to get a meaningful representation
                repr_str = repr(obj)
                if len(repr_str) > cls.MAX_LOCALS_VALUE_LENGTH:
                    repr_str = repr_str[: cls.MAX_LOCALS_VALUE_LENGTH] + "..."

                return {
                    "type": f"{obj_module}.{obj_type}" if obj_module else obj_type,
                    "display": repr_str,
                }
            except Exception:
                # Fallback to basic type information
                return {
                    "type": f"{obj_module}.{obj_type}" if obj_module else obj_type,
                    "display": f"<{obj_type} object>",
                }

        except Exception as e:
            return {
                "type": "unknown",
                "display": f"<serialization error: {str(e)[:50]}>",
            }
        finally:
            seen.discard(obj_id)

    @classmethod
    def _get_source_context(
        cls, filename: str, lineno: int, context_lines: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Get source code context around a line."""
        try:
            lines = []

            start = max(1, lineno - context_lines)
            end = lineno + context_lines + 1

            for i in range(start, end):
                line = linecache.getline(filename, i)
                if line:
                    lines.append(
                        {"lineno": i, "code": line.rstrip(), "current": i == lineno}
                    )

            return {"lines": lines, "start": start, "end": end - 1} if lines else None
        except Exception:
            return None
