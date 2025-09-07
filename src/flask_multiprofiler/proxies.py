# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
from flask import current_app
from werkzeug.local import LocalProxy

current_multiprofiler = LocalProxy(lambda: current_app.extensions["multiprofiler"])
"""Proxy for the multi-profiler extension."""
