def test_upload_rejects_non_csv(client) -> None:
    response = client.post(
        "/parquet/upload_file",
        files={"file": ("notes.txt", b"not a csv", "text/plain")},
    )
    assert response.status_code == 400
    assert "csv" in response.json()["detail"].lower()
