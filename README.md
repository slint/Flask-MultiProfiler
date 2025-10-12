# Flask-MultiProfiler

A Flask extension that provides multi-dimensional profiling capabilities for Flask applications.

## Features

- **Code profiling**: Statistical profiling using [pyinstrument](https://pyinstrument.readthedocs.io/en/latest/home.html) to identify performance bottlenecks
- **SQL profiling**: Database query profiling using [sqltap](https://github.com/inconshreveable/sqltap) to track query performance
- **Search profiling**: Custom profiler for [OpenSearch](https://opensearch.org/)/[Elasticsearch](https://www.elastic.co/elasticsearch/) operations via trace logging

## Installation

```bash
pip install flask-multiprofiler
```

For search profiling support, install with the appropriate extra:

```bash
# For OpenSearch
pip install flask-multiprofiler[opensearch]

# For Elasticsearch
pip install flask-multiprofiler[elasticsearch]
```

## Quick Start

```python
from flask import Flask
from flask_multiprofiler import MultiProfiler

app = Flask(__name__)
profiler = MultiProfiler(app)

# Or using the factory pattern
profiler = MultiProfiler()
profiler.init_app(app)
```

## Usage

1. Navigate to `/profiler` in your Flask application
2. Start a profiling session by selecting which profilers to enable
3. Use your application normally - profiling data is collected automatically
4. View profiling reports through the web interface

## Configuration

```python
# Storage directory for profiling sessions (default: "{Flask.instance_path}/profiler")
MULTIPROFILER_STORAGE = "/path/to/storage"

# Logger name for search profiling (default: "opensearchpy.trace")
MULTIPROFILER_SEARCH_TRACE_LOGGER = "elasticsearchpy.trace"

# Session lifetime (default: 60 minutes)
MULTIPROFILER_ACTIVE_SESSION_LIFETIME = timedelta(minutes=30)

# Endpoints to ignore during profiling (regex patterns)
MULTIPROFILER_IGNORED_ENDPOINTS = ["static", r"profiler\..+", "api.health"]

# Permission function (default: lambda: True)
MULTIPROFILER_PERMISSION = lambda: current_user.is_admin
```

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) for dependency management and [`just`](https://github.com/casey/just) for task automation. Tests use [`testcontainers`](https://testcontainers-python.readthedocs.io/) to run PostgreSQL and OpenSearch in Docker containers.

```bash
# Run tests (automatically installs dependencies)
just test

# Run specific tests or with custom pytest flags
just test tests/test_extension.py
just test -v -k "test_specific"

# Format code
just format

# Lint and auto-fix
just lint
```

## Architecture

- Each profiling session creates its own SQLite database for storing profiling reports in a self-contained HTML format
- Profilers can be enabled/disabled individually per session
- Web interface provides session management and report viewing

## Search Profiler Compatibility

The search profiler currently supports:
- OpenSearch client (opensearch-py)
- Elasticsearch client v7.x only (elasticsearch~=7.17.12)

Both clients use the same logging mechanism (plain Python logger) for trace logging, which our profiler intercepts. Elasticsearch v8.x uses a different tracing approach and is not currently supported.

## Future Development

Planned features and improvements:

- **Redis profiling**: Track Redis operations and performance
- **Enhanced search query viewer**: Improved visualization and analysis of search queries
- **SQL profiler rewrite**: Replace sqltap with custom implementation to add stack traces and better integration

## Non-Goals

This module intentionally keeps things simple and will **not** support:

- **Customizing rendering**: Reports are stored as fully renderable HTML pages to keep complexity low
- **REST API**: No plans to expose profiling data via API endpoint
- **Async support**: Focused on traditional Flask applications only
- **Full type hints**: Minimal type annotations to maintain simplicity
- **Translations/I18N**: This is an sysadmin/developer interface
