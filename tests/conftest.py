from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.config import reset_settings_cache
from app.server import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    # Isolate test data writes
    import os
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as d:
        os.environ["DATA_DIR"] = d
        os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
        os.environ.setdefault("DATASET_TOOL_ROUTER_ENABLED", "false")
        reset_settings_cache()
        with TestClient(app) as test_client:
            yield test_client
    reset_settings_cache()
