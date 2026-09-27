import {poiPopupHtml} from './mapPoiPopup';

// Clicking a POI on the map opens a popup built from attributes already in the pmtiles
// file: the name, its category (kind), sub-category (kind_detail), and elevation.

const feature = (properties) => ({properties});

test('name, kind, detail and elevation are all shown, humanized', () => {
    const html = poiPopupHtml([feature({
        name: 'Flattop Mountain', kind: 'peak', kind_detail: 'volcano', elevation: 1070,
    })]);
    expect(html).toContain('Flattop Mountain');
    expect(html).toContain('Peak');
    expect(html).toContain('Volcano');
    expect(html).toContain('1070 m');
    expect(html).toContain('3510 ft');
});

test('missing attributes are left out rather than shown as undefined', () => {
    const html = poiPopupHtml([feature({name: 'Franz', kind: 'bakery'})]);
    expect(html).toContain('Franz');
    expect(html).toContain('Bakery');
    expect(html).not.toContain('undefined');
    expect(html).not.toContain('Elevation');
});

test('kind_detail of "none" is not shown', () => {
    const html = poiPopupHtml([feature({name: 'West High', kind: 'school', kind_detail: 'none'})]);
    expect(html).not.toContain('none');
    expect(html).not.toContain('None');
});

test('the same feature at several min_zoom levels appears once', () => {
    const html = poiPopupHtml([
        feature({name: 'Westchester Lagoon', kind: 'water', min_zoom: 12}),
        feature({name: 'Westchester Lagoon', kind: 'water', min_zoom: 14}),
    ]);
    expect(html.match(/Westchester Lagoon/g)).toHaveLength(1);
});

test('feature properties are HTML escaped', () => {
    const html = poiPopupHtml([feature({name: '<img src=x onerror=alert(1)>', kind: 'a&b'})]);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
    expect(html).toContain('A&amp;b');
});

test('a point feature shows its own coordinates, lat then lon', () => {
    const html = poiPopupHtml([{
        properties: {name: 'Peak Two', kind: 'peak'},
        geometry: {type: 'Point', coordinates: [-149.67301, 61.08571]},
    }], {lng: -149.5, lat: 61.0});
    expect(html).toContain('61.08571, -149.67301');
});

test('a feature without a point falls back to the clicked location', () => {
    const html = poiPopupHtml([feature({name: 'Lagoon', kind: 'water'})], {lng: -149.5, lat: 61.0});
    expect(html).toContain('61.00000, -149.50000');
});

test('no features gives no popup', () => {
    expect(poiPopupHtml([])).toBeNull();
});
