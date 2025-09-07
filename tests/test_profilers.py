# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
import pytest
from bs4 import BeautifulSoup

from flask_multiprofiler.profilers import (
    CodeProfiler,
    SearchProfiler,
    SQLProfiler,
)


class TestCodeProfiler:
    """Test the CodeProfiler implementation."""

    def test_code_profiler_initialization(self):
        """Test that CodeProfiler initializes in a ready-to-start state."""
        profiler = CodeProfiler()

        # Should be ready to start profiling
        profiler.start()
        assert profiler.profiler is not None

        # Should be able to stop cleanly
        profiler.stop()

        # Should be able to cleanup
        profiler.cleanup()

    def test_code_profiler_start_stop(self):
        """Test starting and stopping code profiler."""
        profiler = CodeProfiler()

        profiler.start()
        assert profiler.profiler is not None

        profiler.stop()
        # Profiler should still exist after stop, just not running

    def test_code_profiler_collect_report_without_profiling(self):
        """Test collecting report when no profiling was done."""
        profiler = CodeProfiler()
        report = profiler.collect_report()
        assert report is None

    def test_code_profiler_collect_report_after_start_stop(self):
        """Test collecting report after profiling."""
        profiler = CodeProfiler()

        profiler.start()
        # Do some work
        sum(range(100))
        profiler.stop()

        report = profiler.collect_report()
        assert report is not None
        assert isinstance(report, str)

        # Validate proper HTML structure using BeautifulSoup
        soup = BeautifulSoup(report, "html.parser")
        assert soup is not None

        # Should have proper HTML document structure
        assert soup.find("html") is not None
        assert soup.find("head") is not None
        assert soup.find("body") is not None

        # pyinstrument generates a single-page app with div#app
        assert soup.find("div", {"id": "app"}) is not None

        # Should contain JavaScript with profiling data
        scripts = soup.find_all("script")
        assert len(scripts) > 0
        script_content = " ".join(script.get_text() for script in scripts)
        assert (
            "pyinstrument" in script_content.lower()
            or "profil" in script_content.lower()
        )


class TestSQLProfiler:
    """Test the SQLProfiler implementation."""

    def test_sql_profiler_initialization(self):
        """Test that SQLProfiler initializes in a ready-to-start state."""
        profiler = SQLProfiler()

        # Should be ready to start profiling
        profiler.start()
        assert profiler.profiler is not None

        # Should be able to stop cleanly
        profiler.stop()

        # Should be able to cleanup
        profiler.cleanup()

    def test_sql_profiler_start_stop(self):
        """Test starting and stopping SQL profiler."""
        profiler = SQLProfiler()

        profiler.start()
        assert profiler.profiler is not None

        profiler.stop()
        # Profiler should still exist after stop

    def test_sql_profiler_collect_report_without_queries(self):
        """Test collecting report when no SQL queries were executed."""
        profiler = SQLProfiler()

        profiler.start()
        profiler.stop()

        report = profiler.collect_report()
        # Should return None when no SQL queries were executed
        assert report is None


class TestSearchProfiler:
    """Test the SearchProfiler implementation."""

    def test_search_profiler_initialization(self):
        """Test that SearchProfiler can be instantiated."""
        profiler = SearchProfiler("test.logger")
        assert profiler.logger_name == "test.logger"
        assert profiler.collector is None
        assert profiler.logger is None

    def test_search_profiler_start_stop(self):
        """Test starting and stopping search profiler."""
        profiler = SearchProfiler("test.logger")

        profiler.start()
        assert profiler.logger is not None
        assert profiler.collector is not None
        assert profiler.original_level is not None

        profiler.stop()
        # Components should still exist after stop

    def test_search_profiler_collect_report_without_queries(self):
        """Test collecting report when no search queries were captured."""
        profiler = SearchProfiler("test.logger")

        profiler.start()
        profiler.stop()

        report = profiler.collect_report()
        assert report is not None
        assert isinstance(report, str)
        assert "No search queries recorded" in report

    def test_search_profiler_cleanup(self):
        """Test cleanup of search profiler resources."""
        profiler = SearchProfiler("test.logger")

        profiler.start()
        original_handlers_count = len(profiler.logger.handlers)

        profiler.cleanup()

        # Handler should be removed during cleanup
        final_handlers_count = len(profiler.logger.handlers)
        assert final_handlers_count < original_handlers_count


class TestProfilerImplementations:
    """Test that all profilers implement the BaseProfiler interface correctly."""

    @pytest.mark.parametrize(
        "profiler_class,init_args",
        [
            (CodeProfiler, []),
            (SQLProfiler, []),
            (SearchProfiler, ["test.logger"]),
        ],
    )
    def test_profiler_implements_base_interface(self, profiler_class, init_args):
        """Test that profilers implement the expected behavior."""
        profiler = profiler_class(*init_args)

        # Test that all interface methods work correctly
        profiler.start()
        profiler.stop()
        report = profiler.collect_report()
        assert report is None or isinstance(report, str)
        profiler.cleanup()

    @pytest.mark.parametrize(
        "profiler_class,init_args",
        [
            (CodeProfiler, []),
            (SQLProfiler, []),
            (SearchProfiler, ["test.logger"]),
        ],
    )
    def test_profiler_lifecycle(self, profiler_class, init_args):
        """Test complete profiler lifecycle."""
        profiler = profiler_class(*init_args)

        # Should be able to start
        profiler.start()

        # Should be able to stop
        profiler.stop()

        # Should be able to collect report
        report = profiler.collect_report()
        assert report is None or isinstance(report, str)

        # Should be able to cleanup
        profiler.cleanup()
