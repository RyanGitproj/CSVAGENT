from app.services.dataset_tool_router import (
    _assistant_snippet_for_router,
    parse_router_output_implies_file_lookup,
)


def test_parse_lookup_explicit() -> None:
    assert parse_router_output_implies_file_lookup("LOOKUP") is True
    assert parse_router_output_implies_file_lookup("lookup\n") is True


def test_parse_chat_explicit() -> None:
    assert parse_router_output_implies_file_lookup("CHAT") is False
    assert parse_router_output_implies_file_lookup("CHAT — continuation") is False


def test_parse_default_safe_lookup() -> None:
    assert parse_router_output_implies_file_lookup("") is True
    assert parse_router_output_implies_file_lookup("maybe") is True


def test_assistant_snippet_keeps_head_and_tail() -> None:
    long = "START_LIST item1 item2 " + ("x" * 5_000) + " END_RECENT tail"
    s = _assistant_snippet_for_router(long, max_chars=800, head_chars=40)
    assert "START_LIST" in s
    assert "END_RECENT" in s
    assert len(s) <= 850
