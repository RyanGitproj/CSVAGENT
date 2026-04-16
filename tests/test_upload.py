def test_ingest_tabular_rejects_non_tabular(client) -> None:
    ds = client.post("/datasets", json={"name": "Demo"}).json()
    response = client.post(
        f"/datasets/{ds['id']}/ingest/tabular",
        files={"file": ("notes.txt", b"not a table", "text/plain")},
    )
    assert response.status_code == 400
    assert "csv" in response.json()["detail"].lower() or "xlsx" in response.json()["detail"].lower()


def test_ask_without_ingest_returns_404(client) -> None:
    ds = client.post("/datasets", json={"name": "Demo"}).json()
    response = client.post(f"/datasets/{ds['id']}/ask", json={"question": "Combien de lignes ?", "mode": "tabular"})
    assert response.status_code in (404, 400)
