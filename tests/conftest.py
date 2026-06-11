from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_redis() -> MagicMock:
    return MagicMock()