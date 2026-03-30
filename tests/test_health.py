def test_health_returns_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_docs(client) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 308, 302)
    assert response.headers["location"].endswith("/docs")
