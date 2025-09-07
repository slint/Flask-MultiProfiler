# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import sqlalchemy as sa
from flask import current_app, g, request
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.pool import SingletonThreadPool

Base = declarative_base()


class SessionRequest(Base):
    """Profiling session requests model."""

    __tablename__ = "session_requests"

    id = sa.Column(sa.Integer, primary_key=True)
    ts = sa.Column(sa.DateTime)
    context = sa.Column(sa.JSON)
    code_report = sa.Column(sa.Text)
    sql_report = sa.Column(sa.Text)
    search_report = sa.Column(sa.Text)


class classproperty:
    def __init__(self, func):
        self.fget = func

    def __get__(self, instance, owner):
        return self.fget(owner)


class ProfileSessions:
    @classproperty
    def storage_dir(cls):
        """Profiling sessions storage directory path from config."""
        return Path(current_app.config["MULTIPROFILER_STORAGE"])

    @classmethod
    @contextmanager
    def db_session(cls, session_id=None) -> Generator[Session, None, None]:
        """Context manager for SQLAlchemy session with automatic cleanup."""
        db_path = cls.storage_dir / f"{session_id or g.profiler_session_id}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = sa.create_engine(f"sqlite:///{db_path}", poolclass=SingletonThreadPool)
        Base.metadata.create_all(engine)

        try:
            with Session(bind=engine) as session:
                yield session
        finally:
            engine.dispose()

    @classmethod
    def get_session_entries(cls, session_id):
        """Get profiling session request entries for a session."""
        with cls.db_session(session_id) as session:
            return (
                session.query(
                    SessionRequest.id,
                    SessionRequest.ts,
                    SessionRequest.context,
                    SessionRequest.code_report.is_not(None).label("has_code_report"),
                    SessionRequest.sql_report.is_not(None).label("has_sql_report"),
                    SessionRequest.search_report.is_not(None).label(
                        "has_search_report"
                    ),
                )
                .order_by(SessionRequest.ts.asc())
                .all()
            )

    @classmethod
    def get_all_sessions(cls):
        """List profiler sessions information."""
        if cls.storage_dir.exists():
            return {
                sess_db.stem: cls.get_session_entries(sess_db.stem)
                for sess_db in cls.storage_dir.iterdir()
                if sess_db.is_file() and sess_db.suffix == ".db"
            }
        return {}

    @classmethod
    def clear_sessions(cls):
        """Delete all profiling sesions files from storage."""
        for sess_db in cls.storage_dir.iterdir():
            if sess_db.is_file() and sess_db.suffix == ".db":
                sess_db.unlink(missing_ok=True)

    @classmethod
    def get_request_report(cls, session_id, request_id, report_type):
        """Retrieve raw HTML report type for a specific profiling session request."""
        with cls.db_session(session_id) as session:
            if report_type == "sql":
                query = session.query(SessionRequest.sql_report)
            elif report_type == "code":
                query = session.query(SessionRequest.code_report)
            elif report_type == "search":
                query = session.query(SessionRequest.search_report)
            else:
                return None
            return query.filter(SessionRequest.id == request_id).scalar()

    @classmethod
    def store_session_request(cls, reports):
        """Store profiling reports and context for a request in a session."""
        with cls.db_session() as session:
            session.add(
                SessionRequest(
                    ts=datetime.now(timezone.utc),
                    context={
                        "endpoint": request.endpoint,
                        "url": request.url,
                        "path": request.path,
                        "method": request.method,
                        "referrer": request.referrer,
                        "headers": dict(request.headers),
                    },
                    code_report=reports.get("code"),
                    sql_report=reports.get("sql"),
                    search_report=reports.get("search"),
                )
            )
            session.commit()
