# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Flask-MultiProfiler is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Test application components for Flask-MultiProfiler testing."""

import hashlib
import json
from datetime import datetime

from flask import Blueprint, current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship("Post", backref="author", lazy="dynamic")


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship("Comment", backref="post", lazy="dynamic")


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")


test_bp = Blueprint("test", __name__)


@test_bp.route("/compute")
def compute():
    """Multiple computational operations to show different function performance."""

    def calculate_sum(n=1000):
        return sum(range(n))

    def process_strings(iterations=100):
        results = []
        for i in range(iterations):
            text = f"Processing string number {i}" * 10
            results.append(text.upper().replace(" ", "_"))
        return len("".join(results))

    def compute_hashes(iterations=500):
        hashes = []
        for i in range(iterations):
            data = f"data-{i}".encode()
            h = hashlib.sha256(data)
            for _ in range(10):
                h = hashlib.sha256(h.digest())
            hashes.append(h.hexdigest())
        return hashes[-1]

    def json_processing(size=100):
        data = {
            f"key_{i}": {"value": i, "nested": {f"sub_{j}": j for j in range(10)}}
            for i in range(size)
        }

        for _ in range(5):
            json_str = json.dumps(data, indent=2)
            data = json.loads(json_str)

        return len(json_str)

    results = {
        "sum_result": calculate_sum(10000),
        "string_length": process_strings(200),
        "last_hash": compute_hashes(100),
        "json_size": json_processing(50),
    }

    return results


@test_bp.route("/queries")
def queries():
    """Execute queries across multiple tables for SQL profiling."""
    total_users = User.query.count()
    active_users = User.query.filter_by(active=True).all()

    user_posts = (
        db.session.query(User.name, func.count(Post.id).label("post_count"))
        .join(Post)
        .group_by(User.id)
        .all()
    )

    recent_comments = (
        db.session.query(Comment.content, User.name, Post.title)
        .select_from(Comment)
        .join(Post)
        .join(User, Comment.user_id == User.id)
        .order_by(Comment.created_at.desc())
        .limit(10)
        .all()
    )

    stats = (
        db.session.query(
            func.count(User.id).label("users"),
            func.count(Post.id).label("posts"),
            func.count(Comment.id).label("comments"),
            func.avg(func.length(Post.content)).label("avg_post_length"),
        )
        .select_from(User)
        .outerjoin(Post)
        .outerjoin(Comment)
        .first()
    )

    top_posters = (
        db.session.query(User)
        .filter(
            User.id.in_(
                db.session.query(Post.user_id)
                .group_by(Post.user_id)
                .having(func.count(Post.id) > 1)
            )
        )
        .all()
    )

    return {
        "total_users": total_users,
        "active_users": len(active_users),
        "user_posts": len(user_posts),
        "recent_comments": len(recent_comments),
        "stats": {
            "users": stats.users,
            "posts": stats.posts,
            "comments": stats.comments,
            "avg_post_length": float(stats.avg_post_length)
            if stats.avg_post_length
            else 0,
        },
        "top_posters": len(top_posters),
    }


@test_bp.route("/dashboard")
def dashboard():
    """Endpoint that triggers all profiler types for comprehensive testing."""
    hash_result = hashlib.sha256(b"dashboard-data").hexdigest()
    computed_sum = sum(range(1000))

    user_count = User.query.count()
    post_stats = db.session.query(
        func.count(Post.id).label("total_posts"),
        func.avg(func.length(Post.content)).label("avg_length"),
    ).first()

    search_query = "dashboard content"

    return {
        "dashboard_hash": hash_result,
        "computed_sum": computed_sum,
        "user_count": user_count,
        "post_stats": {
            "total_posts": post_stats.total_posts,
            "avg_length": float(post_stats.avg_length) if post_stats.avg_length else 0,
        },
        "search_query": search_query,
        "timestamp": datetime.utcnow().isoformat(),
    }


@test_bp.route("/search/<query>")
def search(query):
    """Search documents using OpenSearch client."""
    client = current_app.extensions["opensearch"]

    results = client.search(
        index="test-index", body={"query": {"match": {"content": query}}}
    )

    aggs = client.search(
        index="test-index",
        body={
            "size": 0,
            "aggs": {"categories": {"terms": {"field": "category.keyword"}}},
        },
    )

    return {
        "results": results["hits"]["total"]["value"],
        "categories": len(aggs["aggregations"]["categories"]["buckets"]),
    }


@test_bp.route("/search/malformed-test")
def search_malformed():
    """Search endpoint that simulates malformed responses to test profiler resilience."""
    client = current_app.extensions["opensearch"]

    # Create intentionally problematic query to test parsing resilience
    results = client.search(
        index="test-index",
        body={"query": {"match": {"content": 'malformed-test "unclosed quote'}}},
    )
    return {"results": results["hits"]["total"]["value"]}


@test_bp.route("/search/duplicate-test")
def search_duplicate():
    """Search endpoint for testing deduplication behavior."""
    client = current_app.extensions["opensearch"]

    # Same query each time to test deduplication
    results = client.search(
        index="test-index",
        body={"query": {"match": {"content": "duplicate search query"}}},
    )
    return {
        "results": results["hits"]["total"]["value"],
        "timestamp": datetime.utcnow().isoformat(),
    }
