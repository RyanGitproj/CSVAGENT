def test_preview_tabular_after_ingest(client) -> None:
    ds = client.post("/datasets", json={"name": "Prev"}).json()
    csv = "col_a,col_b\n1,hello\n2,world\n"
    ing = client.post(
        f"/datasets/{ds['id']}/ingest/tabular",
        files={"file": ("sample.csv", csv.encode("utf-8"), "text/csv")},
    )
    assert ing.status_code == 200
    fl = client.get(f"/datasets/{ds['id']}/files").json()
    assert fl["files"]
    sn = fl["files"][0]["stored_name"]
    prev = client.get(f"/datasets/{ds['id']}/files/{sn}/preview")
    assert prev.status_code == 200
    body = prev.json()
    assert body["kind"] == "tabular"
    assert "col_a" in body["columns"]
    assert len(body["rows"]) >= 1
    raw = client.get(f"/datasets/{ds['id']}/files/{sn}/raw")
    assert raw.status_code == 200
    assert len(raw.content) > 0


def test_preview_unknown_file_404(client) -> None:
    ds = client.post("/datasets", json={"name": "X"}).json()
    r = client.get(f"/datasets/{ds['id']}/files/nope.csv/preview")
    assert r.status_code == 404
