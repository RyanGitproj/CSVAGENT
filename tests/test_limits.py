def test_limits_endpoint(client) -> None:
    r = client.get("/limits")
    assert r.status_code == 200
    body = r.json()
    assert "max_upload_mb" in body
    assert "max_table_rows" in body
    assert "max_workspace_files" in body
    assert "rate_limit_enabled" in body
    assert "rate_limit_per_minute" in body
    assert "preview_max_pdf_pages" in body
    assert "preview_max_tabular_rows" in body
    assert "chat_history_max_messages" in body
    assert "conversation_context_max_messages" in body
    assert "conversation_context_max_chars_per_message" in body
    assert "dataset_tool_router_enabled" in body
    assert "dataset_router_snippet_chars" in body
    assert "dataset_router_max_output_tokens" in body
    assert "dataset_agent_max_steps" in body
    assert "dataset_agent_wall_seconds" in body
    assert "dataset_agent_repeat_tool_limit" in body
    assert "dataset_router_model" in body
    assert "dataset_ask_quota_per_conversation_per_minute" in body
    assert "pdf_retrieval_cache_ttl_seconds" in body
    assert "pdf_ocr_enabled" in body
    assert "conversation_summary_enabled" in body
    assert "conversation_summary_every_n_messages" in body
    assert "conversation_summary_max_chars" in body
    assert "ask_request_log_enabled" in body
    assert isinstance(body["max_workspace_files"], int)


def test_ask_quota_per_conversation_enforced(client, monkeypatch) -> None:
    # Plancher config : 5 (voir ``dataset_ask_quota_per_conversation_per_minute``).
    monkeypatch.setenv("DATASET_ASK_QUOTA_PER_CONV_PER_MIN", "5")
    from app.config import reset_settings_cache

    reset_settings_cache()
    ds = client.post("/datasets", json={"name": "Quota"}).json()
    cid = "quota-test-conv-unique"
    # 1 unité par tour en mode docs ; pas d’index PDF → 404 après consommation quota.
    body = {"question": "x", "mode": "docs", "conversation_id": cid}
    url = f"/datasets/{ds['id']}/ask"
    for _ in range(5):
        assert client.post(url, json=body).status_code == 404
    r6 = client.post(url, json=body)
    assert r6.status_code == 429
    assert "quota" in r6.json()["detail"].lower() or "unités" in r6.json()["detail"].lower()
