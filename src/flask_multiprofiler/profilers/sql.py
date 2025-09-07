# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
from typing import Optional

import sqltap

from .base import BaseProfiler


class SQLProfiler(BaseProfiler):
    """Profiler for SQL queries using sqltap."""

    def __init__(self):
        self.profiler = None

    def start(self):
        """Start SQL profiling."""
        self.profiler = sqltap.ProfilingSession()
        self.profiler.start()

    def stop(self):
        """Stop SQL profiling."""
        if self.profiler:
            self.profiler.stop()

    def collect_report(self) -> Optional[str]:
        """Collect HTML report from sqltap."""
        if self.profiler:
            stats = self.profiler.collect()
            if stats:
                return sqltap.report(stats, report_format="html")
        return None
