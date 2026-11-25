import pytest
from fastapi.testclient import TestClient

from site_monitor.main import app


@pytest.fixture
def client(tmp_path, monkeypatch, fake_dns):
    # Point the app at a fresh database file for each test.
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    # `with` runs the lifespan (startup), which creates the table.
    with TestClient(app) as client:
        yield client


def test_list_is_empty_at_start(client):
    response = client.get("/targets")

    assert response.status_code == 200
    assert response.json() == []


def test_create_target(client):
    response = client.post("/targets", json={"url": "https://example.com"})

    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://example.com/"  # normalized
    assert isinstance(body["id"], int)
    assert body["created_at"]


def test_created_target_is_listed(client):
    client.post("/targets", json={"url": "https://example.com"})

    urls = [t["url"] for t in client.get("/targets").json()]
    assert urls == ["https://example.com/"]


def test_duplicate_target_returns_409(client):
    client.post("/targets", json={"url": "https://example.com"})

    # Same site, different spelling: normalization makes it a duplicate.
    response = client.post("/targets", json={"url": "HTTPS://EXAMPLE.com/"})

    assert response.status_code == 409


@pytest.mark.parametrize(
    "url",
    [
        "",
        "example.com",  # no scheme
        "ftp://example.com",  # not http/https
        "javascript:alert(1)",
        "https://user:secret@example.com",  # credentials
        "https://" + "a" * 2100 + ".com",  # too long
    ],
)
def test_invalid_url_returns_422(client, url):
    response = client.post("/targets", json={"url": url})

    assert response.status_code == 422


def test_missing_url_field_returns_422(client):
    response = client.post("/targets", json={})

    assert response.status_code == 422


def test_delete_target(client):
    created = client.post("/targets", json={"url": "https://example.com"})
    target_id = created.json()["id"]

    response = client.delete(f"/targets/{target_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/targets").json() == []


def test_delete_unknown_target_returns_404(client):
    response = client.delete("/targets/999")

    assert response.status_code == 404


def test_delete_with_non_integer_id_returns_422(client):
    response = client.delete("/targets/abc")

    assert response.status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9090/",
        "http://localhost/",
        "http://2130706433/",  # 127.0.0.1 written as a decimal number
        "http://169.254.169.254/latest/meta-data/",
        "https://internal.example/",  # hostname resolving to 10.0.0.5
        "https://mixed.example/",  # one public and one loopback address
    ],
)
def test_non_public_targets_are_rejected(client, url):
    response = client.post("/targets", json={"url": url})

    assert response.status_code == 422
    # Check the reason, so the test cannot pass for an unrelated error.
    assert "non-public address" in response.json()["detail"]
    assert client.get("/targets").json() == []


def test_unresolvable_target_is_rejected(client):
    response = client.post("/targets", json={"url": "https://nope.example/"})

    assert response.status_code == 422
    assert "does not resolve" in response.json()["detail"]
