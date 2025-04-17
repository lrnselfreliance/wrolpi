from http import HTTPStatus

import pytest

from wrolpi.common import get_wrolpi_config
from wrolpi.tags import Tag


@pytest.mark.asyncio
async def test_configs_crud(async_client, test_session, test_tags_config, tag_factory, test_wrolpi_config,
                            test_channels_config, await_switches):
    """Configs can be imported or saved on demand."""
    # Create a tag, save it to config, delete it from the DB.
    one = await tag_factory()
    test_session.commit()
    await await_switches()
    test_session.delete(one)
    test_session.commit()
    assert 'one' in test_tags_config.read_text()
    assert test_session.query(Tag).count() == 0, 'Tag should have been deleted'

    # Can get list of configs, and if they are valid.
    request, response = await async_client.get('/api/config')
    assert response.status_code == HTTPStatus.OK
    # WROLPiConfig was not saved.
    assert 'wrolpi.yaml' in response.json['configs']
    assert response.json['configs']['wrolpi.yaml']['valid'] is None
    assert response.json['configs']['wrolpi.yaml']['successful_import'] is False
    # Tags was saved, and is valid.
    assert 'tags.yaml' in response.json['configs']
    assert response.json['configs']['tags.yaml']['valid'] is True
    assert response.json['configs']['wrolpi.yaml']['successful_import'] is False

    # Can import the config.
    body = dict(file_name='tags.yaml')
    request, response = await async_client.post('/api/config/import', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT
    # Deleted Tag was re-created.
    assert [i for i, in test_session.query(Tag.name)] == ['one', ]

    # Can trigger a save of a config
    assert not test_wrolpi_config.exists()
    body = dict(file_name='wrolpi.yaml')
    request, response = await async_client.post('/api/config/dump', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_wrolpi_config.is_file()
    assert 'wrol_mode:' in test_wrolpi_config.read_text()

    # Config is now valid because it exists.
    request, response = await async_client.get('/api/config')
    assert response.status_code == HTTPStatus.OK
    assert 'wrolpi.yaml' in response.json['configs']
    assert response.json['configs']['wrolpi.yaml']['valid'] is True
    assert response.json['configs']['tags.yaml']['successful_import'] is True

    # Get and change a config.
    request, response = await async_client.get('/api/config?file_name=wrolpi.yaml')
    assert response.status_code == HTTPStatus.OK
    wrolpi_config = response.json['config']
    assert wrolpi_config['archive_destination'] == 'archive/%(domain)s'
    # Change config value.
    wrolpi_config['archive_destination'] = 'some new value'
    body = dict(config=wrolpi_config)
    # Update the config file.
    request, response = await async_client.post('/api/config?file_name=wrolpi.yaml', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert 'some new value' in get_wrolpi_config().get_file().read_text()
