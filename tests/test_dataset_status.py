def test_dataset_ingest_status_empty(client) -> None:
    ds = client.post("/datasets", json={"name": "Demo"}).json()
    response = client.get(f"/datasets/{ds['id']}/ingest/status")
    assert response.status_code == 200
    j = response.json()
    assert j["dataset_id"] == ds["id"]
    assert j["has_tabular"] is False
    assert j["has_pdf"] is False


def test_dataset_ingest_status_unknown(client) -> None:
    response = client.get("/datasets/00000000-0000-0000-0000-000000000000/ingest/status")
    assert response.status_code == 404
