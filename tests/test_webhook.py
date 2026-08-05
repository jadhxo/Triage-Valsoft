from fastapi.testclient import TestClient


def test_valid_authenticated_webhook_returns_202(client, payload, auth_headers):
    response = client.post("/webhooks/intake", json=payload, headers=auth_headers)
    assert response.status_code == 202
    assert response.json() == {
        "accepted": True,
        "duplicate": False,
        "event_id": "evt-001",
        "status": "accepted",
    }


def test_invalid_payload_returns_422(client, auth_headers):
    response = client.post(
        "/webhooks/intake",
        json={"event_id": " ", "source": "Carrier Pigeon", "message": " "},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_missing_or_invalid_secret_returns_401(client, payload):
    assert client.post("/webhooks/intake", json=payload).status_code == 401
    assert (
        client.post(
            "/webhooks/intake", json=payload, headers={"X-Webhook-Secret": "wrong"}
        ).status_code
        == 401
    )


def test_authentication_precedes_payload_validation(client):
    assert client.post("/webhooks/intake", json={}).status_code == 401


def test_unknown_lookup_returns_404(client):
    assert client.get("/requests/unknown").status_code == 404


def test_completed_lookup_returns_record(client, payload, auth_headers):
    client.post("/webhooks/intake", json=payload, headers=auth_headers)
    response = client.get("/requests/evt-001")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["record"]["event_id"] == "evt-001"
    assert body["record"]["category"] == "Bug Report"


def test_health_exposes_no_configuration(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}
