# AI module test fixtures.  The docs conftest is not star-imported by the root conftest, but the
# AI endpoints cover docs; import its fixtures so AI tests can use doc_factory.
import pytest

from modules.ai.config import ai_config_context
from modules.docs.conftest import *  # noqa
from wrolpi.api_utils import api_app


@pytest.fixture
def test_ai_config(test_directory, async_client):
    """An isolated ai.yaml config for one test."""
    (test_directory / 'config').mkdir(exist_ok=True)
    config_path = test_directory / 'config/ai.yaml'
    with ai_config_context() as config:
        config.initialize(api_app.shared_ctx.ai_config)
        yield config_path
