# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
import tempfile
from pathlib import Path

import pytest
from flask import Flask
from testcontainers.opensearch import OpenSearchContainer
from testcontainers.postgres import PostgresContainer

from flask_multiprofiler import MultiProfiler
from tests.testapp import Comment, Post, User, db, test_bp


@pytest.fixture(scope="session")
def db_uri():
    """Provide a PostgreSQL container for testing."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def search_client():
    """Provide an OpenSearch container for testing."""
    with OpenSearchContainer(image="opensearchproject/opensearch:2.19.3") as opensearch:
        yield opensearch.get_client()


@pytest.fixture(scope="session")
def db_data(db_uri):
    """Set up database with test data."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_uri)
    db.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        users = [
            User(name=f"Test User {i}", email=f"user{i}@test.com", active=True)
            for i in range(5)
        ]
        for user in users:
            session.add(user)
        session.flush()

        posts = [
            Post(
                title=f"Post {i}",
                content=f"Content for post {i}" * 20,
                user_id=users[i % len(users)].id,
            )
            for i in range(10)
        ]
        for post in posts:
            session.add(post)
        session.flush()

        comments = [
            Comment(
                content=f"Comment {i}",
                user_id=users[i % len(users)].id,
                post_id=posts[i % len(posts)].id,
            )
            for i in range(20)
        ]
        for comment in comments:
            session.add(comment)

        session.commit()

        yield db_uri

    finally:
        session.rollback()
        session.close()
        db.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(scope="session")
def search_data(search_client):
    """Set up search index with test data."""
    test_index = "test-index"

    if not search_client.indices.exists(test_index):
        search_client.indices.create(
            test_index,
            body={
                "mappings": {
                    "properties": {
                        "title": {"type": "text"},
                        "content": {"type": "text"},
                        "category": {"type": "keyword"},
                        "created_at": {"type": "date"},
                    }
                }
            },
        )

    sample_docs = [
        {
            "title": f"Document {i}",
            "content": f"This is the content of document {i}",
            "category": f"category-{i % 3}",
            "created_at": "2024-01-01T00:00:00Z",
        }
        for i in range(10)
    ]

    for doc in sample_docs:
        search_client.index(index=test_index, body=doc)

    search_client.indices.refresh(index=test_index)

    yield search_client

    try:
        search_client.indices.delete(test_index, ignore=[400, 404])
    except Exception:
        pass


@pytest.fixture
def temp_storage():
    """Create a temporary directory for profiler storage."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "profiler"


@pytest.fixture
def app(temp_storage, db_data, search_data):
    """Create a Flask application for testing with all endpoints."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = db_data
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MULTIPROFILER_STORAGE"] = temp_storage

    db.init_app(app)
    MultiProfiler(app)

    app.extensions["opensearch"] = search_data
    app.register_blueprint(test_bp)

    return app
