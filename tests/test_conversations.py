def test_list_conversations_returns_json_list(client) -> None:
    response = client.get("/conversations")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_conversation_messages_empty(client) -> None:
    response = client.get("/conversations/test-conv-empty/messages")
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "test-conv-empty"
    assert body["messages"] == []


def test_delete_conversation_ok(client) -> None:
    response = client.delete("/conversations/test-conv-del")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
