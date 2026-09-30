from uuid import uuid4

import pytest


def create_run(client, variant="healthy"):
    run_id = str(uuid4())
    response = client.post("/fixture/runs", json={"run_id": run_id, "variant": variant})
    assert response.status_code == 200
    return run_id, response.json()


def test_local_application_startup_and_assets(client):
    assert client.get("/health").json()["execution_enabled"] is False
    page = client.get("/")
    assert page.status_code == 200
    assert "Trail backpack" in page.text
    for asset in ("app.js", "style.css"):
        assert client.get(f"/assets/{asset}").status_code == 200
    assert client.get("/assets/arbitrary.js").status_code == 422


@pytest.mark.parametrize(
    "variant",
    [
        "healthy",
        "generic_validation",
        "dead_button",
        "delayed_feedback",
        "hidden_shipping",
        "focus_trap",
    ],
)
def test_defects_are_reproducibly_scoped_to_namespace(client, variant):
    run_id, first = create_run(client, variant)
    active = {key for key, value in first["defects"].items() if value}
    assert active == (set() if variant == "healthy" else {variant})
    assert client.get(f"/fixture/runs/{run_id}").json() == first
    assert client.post("/fixture/runs", json={"run_id": run_id, "variant": variant}).json() == first
    different = "dead_button" if variant == "healthy" else "healthy"
    assert (
        client.post("/fixture/runs", json={"run_id": run_id, "variant": different}).status_code
        == 409
    )


def test_accounts_are_unique_and_reset_only_owned_state(client):
    first, _ = create_run(client)
    second, _ = create_run(client, "dead_button")
    account_a = client.post(f"/fixture/runs/{first}/accounts").json()
    account_b = client.post(f"/fixture/runs/{first}/accounts").json()
    account_other = client.post(f"/fixture/runs/{second}/accounts").json()
    assert len({account_a["id"], account_b["id"], account_other["id"]}) == 3
    assert len({account_a["email"], account_b["email"], account_other["email"]}) == 3
    assert account_a["synthetic"] and account_a["email"].endswith("@fixture.invalid")
    client.post(f"/fixture/runs/{first}/checkout", json={"email": account_a["email"]})
    client.post(f"/fixture/runs/{first}/integration/email", json={"operation": "receipt"})
    other_before = client.get(f"/fixture/runs/{second}").json()
    reset = client.post(f"/fixture/runs/{first}/reset").json()
    assert reset["account_count"] == reset["checkout_attempt_count"] == 0
    assert reset["mock_events"] == []
    assert reset["variant"] == "healthy"
    assert client.get(f"/fixture/runs/{second}").json() == other_before
    assert client.post(f"/fixture/runs/{first}/accounts").json() == account_a


@pytest.mark.parametrize(
    "integration", ["payment", "email", "sms", "webhook", "inventory", "analytics"]
)
def test_integrations_are_local_mocks(client, integration):
    run_id, _ = create_run(client)
    event = client.post(
        f"/fixture/runs/{run_id}/integration/{integration}", json={"operation": "synthetic_check"}
    ).json()
    assert event == {
        "integration": integration,
        "operation": "synthetic_check",
        "mock": True,
        "external_dispatch": False,
    }
    assert client.get(f"/fixture/runs/{run_id}").json()["external_dispatches"] == 0


def test_validation_variants_and_non_transactional_checkout(client):
    healthy, _ = create_run(client)
    generic, _ = create_run(client, "generic_validation")
    for email in ("test.user", "@fixture.invalid", "test@real.invalid", "a b@fixture.invalid"):
        helpful = client.post(f"/fixture/runs/{healthy}/checkout", json={"email": email})
        vague = client.post(f"/fixture/runs/{generic}/checkout", json={"email": email})
        assert helpful.status_code == vague.status_code == 422
        assert helpful.json()["field"] == "email"
        assert vague.json() == {"ok": False, "message": "Invalid input"}
    account = client.post(f"/fixture/runs/{healthy}/accounts").json()
    review = client.post(
        f"/fixture/runs/{healthy}/checkout", json={"email": account["email"]}
    ).json()
    assert review["state"] == "order_review" and review["total"] == 70
    assert review["order_placed"] is False
    assert client.post(f"/fixture/runs/{healthy}/order").status_code == 403
    assert client.get(f"/fixture/runs/{healthy}").json()["real_orders"] == 0


def test_unknown_namespace_and_rejected_sentinel_attempt(client):
    assert client.post(f"/fixture/runs/{uuid4()}/reset").status_code == 404
    result = client.post(
        "/fixture/sentinel/attempt", json={"destination": "https://production.example.invalid"}
    )
    assert result.status_code == 403
    assert result.json()["delivered_requests"] == 0
    assert result.json()["decision"] == "blocked"


def test_invalid_fixture_request_does_not_echo_submitted_secret(client):
    response = client.post("/fixture/runs", json={"run_id": "private-secret-value"})
    assert response.status_code == 422
    assert "private-secret-value" not in response.text
