# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
from abc import ABC, abstractmethod
from typing import Optional


#
# Base Profiler Classes
#
class BaseProfiler(ABC):
    """Abstract base class for profilers."""

    @abstractmethod
    def start(self):
        """Start profiling."""
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        """Stop profiling."""
        raise NotImplementedError

    @abstractmethod
    def collect_report(self) -> Optional[str]:
        """Collect and return profiling report."""
        raise NotImplementedError

    def cleanup(self):
        """Clean up resources. Override if needed."""
        pass
