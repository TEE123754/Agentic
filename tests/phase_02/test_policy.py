import json
from uuid import uuid4

import pytest

from frictionlab.browser.evidence import CoordinateSpace
from frictionlab.contracts.models import TrafficLimits
from frictionlab.fixtures.store import FixtureStore
from frictionlab.protection.policy import FixturePolicy


@pytest.fixture
def policy():
    run_id = uuid4()
    store = FixtureStore()
    store.create(run_id, "healthy")
    store.account(run_id)
    return FixturePolicy("http://127.0.0.1:32145", run_id, "healthy", store, TrafficLimits())


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/fixture/runs/{id}/order", b""),
        ("POST", "/fixture/runs/{id}/order", b"{}"),
        ("POST", "/fixture/runs/{id}/reset", b"{}"),
        ("POST", "/fixture/runs/{id}/integration/payment", b"{}"),
        ("POST", "/fixture/runs/{id}/checkout", b'{"email":"real@company.example"}'),
        ("POST", "/fixture/runs/{id}/checkout", b'{"email":"test.user","secret":"x"}'),
        ("POST", "/fixture/runs/{id}/accounts", b"[]"),
        ("DELETE", "/fixture/runs/{id}/accounts", b"{}"),
        ("GET", "/assets/app.js?live=true", b""),
        ("GET", "/%66ixture/runs/{id}", b""),
        ("GET", "/sw.js", b""),
        ("GET", "/reports/private/html", b""),
    ],
)
def test_operations_and_payloads_are_checked_beyond_method(policy, method, path, body):
    assert policy.reason(method, policy.origin + path.format(id=policy.run_id), body) is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://production.example.invalid/",
        "http://127.0.0.1:32146/assets/app.js",
        "http://localhost:32145/assets/app.js",
        "http://user:secret@127.0.0.1:32145/assets/app.js",
        "http://127.0.0.1:32145/\\evil.invalid",
        "http://127.0.0.1:32145/assets/app.js#secret",
    ],
)
def test_unknown_destinations_fail_closed(policy, url):
    assert policy.reason("GET", url) is not None


def test_only_own_namespace_and_synthetic_payloads_pass(policy):
    url = policy.origin + f"/?run_id={policy.run_id}&variant=healthy"
    assert policy.reason("GET", url) is None
    assert policy.reason("GET", url + "&variant=dead_button") is not None
    assert policy.reason("GET", policy.origin + f"/fixture/runs/{uuid4()}") is not None
    email = next(iter(policy.store.synthetic_emails(policy.run_id)))
    assert (
        policy.reason(
            "POST",
            policy.origin + f"/fixture/runs/{policy.run_id}/checkout",
            json.dumps({"email": email}).encode(),
        )
        is None
    )
    assert policy.reason("GET", policy.origin + "/assets/app.js", upgrade=True) is not None
    policy.stopped.set()
    assert policy.reason("GET", policy.origin + "/assets/app.js") is not None


def test_coordinate_conversion_handles_zoom_offset_and_rejects_outside_pixels():
    space = CoordinateSpace(
        offset_x=10, offset_y=20, css_width=640, css_height=400, pixel_width=1280, pixel_height=800
    )
    assert space.css_to_pixel(100, 100) == (180, 160)
    assert space.pixel_to_css(180, 160) == (100, 100)
    for point in ((-1, 0), (1280, 0), (0, 800)):
        with pytest.raises(ValueError):
            space.pixel_to_css(*point)
