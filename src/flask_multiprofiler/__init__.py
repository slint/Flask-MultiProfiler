# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
from .ext import MultiProfiler
from .proxies import current_multiprofiler

__all__ = ("MultiProfiler", "current_multiprofiler")
