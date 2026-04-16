import pytest
from fastapi import HTTPException

from app.services.sql_qa import _validate_sql


def test_validate_sql_accepts_simple_select() -> None:
    sql = _validate_sql("SELECT col FROM items WHERE id = 1")
    assert "items" in sql.lower()
    assert "limit" in sql.lower()


def test_validate_sql_rejects_empty() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_sql("")
    assert exc.value.status_code == 400


def test_validate_sql_rejects_semicolon() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_sql("SELECT 1 FROM items; DROP TABLE items;")
    assert exc.value.status_code == 400


def test_validate_sql_rejects_non_select() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_sql("INSERT INTO items VALUES (1)")
    assert exc.value.status_code == 400


def test_validate_sql_adds_limit_when_missing() -> None:
    sql = _validate_sql("SELECT * FROM items")
    assert "LIMIT" in sql.upper()
