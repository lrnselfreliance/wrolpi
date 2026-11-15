from http import HTTPStatus

import pytest

from modules.map import quads


def test_load_index():
    souths, rows = quads.load_index()
    assert souths == sorted(souths) == sorted(rows)
    count = 0
    for south in souths:
        wests, cells = quads._row(south)
        assert wests == sorted(wests) == [i[0] for i in cells]
        count += len(cells)
    assert count > 65_000


@pytest.mark.parametrize('west,south,name,state', [
    (-105.125, 40.25, 'Berthoud', 'Colorado'),
    (-108.5, 37.75, 'South Mountain', 'Colorado'),
    (-76.375, 36.375, 'South Mills', 'North Carolina'),
    (-95.25, 37.375, 'South Mound', 'Kansas'),
])
def test_quad_name(west, south, name, state):
    """A quadrangle of the grid has the name the USGS gives it."""
    assert quads.quad_name(west, south, west + 0.125, south + 0.125) == quads.QuadName(name, state, True)
    # Asked with the edges the map has, which are not quite those.
    assert quads.quad_name(west + 1e-7, south - 1e-7, west + 0.125, south + 0.125).exact


def test_quad_name_in_alaska():
    """A quadrangle in Alaska is wider than 7.5 minutes, so an area 7.5 minutes each way is a part of one."""
    assert quads.quad_name(-150, 61.125, -149.875, 61.25) == quads.QuadName('Anchorage A-8 NW', 'Alaska', False)
    # All of it, by its own edges.
    assert quads.quad_name(-150, 61.125, -149.8125, 61.25) == quads.QuadName('Anchorage A-8 NW', 'Alaska', True)
    # The area east of the first is the rest of that quadrangle, and the start of the next.
    assert quads.quad_name(-149.875, 61.125, -149.75, 61.25).name == 'Anchorage A-8 NE'


@pytest.mark.parametrize('west,south,name,state', [
    # A quadrangle 11.25 minutes wide, which ends at the middle of this area: there is none east of it.
    (-153.25, 59.0, 'Iliamna A-1 SW', 'Alaska'),
    (-151.375, 59.0, 'Seldovia A-4 SW', 'Alaska'),
    # A quadrangle moved to fit an island, which ends at the middle of this area: there is none north of it.
    (145.625, 18.75, 'Agrigan Island', 'Northern Mariana Islands'),
])
def test_quad_name_at_an_outer_edge(west, south, name, state):
    """An area half of which is a quadrangle, and the other half no quadrangle, is a part of that quadrangle:
    its middle is on the quadrangle's edge, not outside it."""
    found = quads.quad_name(west, south, west + 0.125, south + 0.125)
    assert found is not None
    assert (found.name, found.state, found.exact) == (name, state, False)


def test_quad_name_at_a_shared_edge():
    """A place on the edge two quadrangles share is in the one east, or north, of that edge."""
    assert quads.quad_name(-105.25, 40.25, -105, 40.375).name == 'Berthoud'
    assert quads.quad_name(-105.125, 40.125, -105, 40.375).name == 'Berthoud'


@pytest.mark.parametrize('west,south', [
    (0, 0),
    (151.125, -33.875),  # Sydney.
    (-105.125, 30),  # Mexico.
    (-40, 40),  # The Atlantic.
    (-180, 84.875),
])
def test_quad_without_a_name(west, south):
    assert quads.quad_name(west, south, west + 0.125, south + 0.125) is None


def test_every_quad_is_found():
    """The middle of each quadrangle of the index is in a quadrangle of that name, or (where two lie over each
    other) of its neighbor's."""
    souths, rows = quads.load_index()
    missed = 0
    for south in souths[::7]:
        wests, cells = quads._row(south)
        for west, east, north, name, state in cells[::5]:
            found = quads.quad_name(west / 3600, south / 3600, east / 3600, north / 3600)
            assert found is not None, (name, state)
            missed += found.name != name
    assert missed <= 2


@pytest.mark.asyncio
async def test_api_quad_name(async_client):
    request, response = await async_client.get('/api/map/quad?west=-105.125&south=40.25&east=-105&north=40.375')
    assert response.status_code == HTTPStatus.OK
    assert response.json == {'quad': {'name': 'Berthoud', 'state': 'Colorado', 'exact': True}}

    # Somewhere the USGS has no name for is not an error.
    request, response = await async_client.get('/api/map/quad?west=0&south=0&east=0.125&north=0.125')
    assert response.status_code == HTTPStatus.OK
    assert response.json == {'quad': None}

    for query in ('', '?west=-105.125&south=40.25&east=-105', '?west=a&south=b&east=c&north=d',
                  '?west=-105.125&south=40.25&east=-113&north=40.375', '?west=nan&south=0&east=1&north=1',
                  '?west=-500&south=0&east=1&north=1'):
        request, response = await async_client.get(f'/api/map/quad{query}')
        assert response.status_code == HTTPStatus.BAD_REQUEST, query
