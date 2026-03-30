GB = 1_000_000_000
MB = 1_000_000

# Manifest URL — points to a JSON file on the CDN that contains the current planet file URL.
MANIFEST_URL = 'https://wrolpi.nyc3.cdn.digitaloceanspaces.com/maps/manifest.json'

# Predefined regions with bounding boxes for pmtiles extract.
# These regions collectively cover the entire planet.
# All regions are kept under ~9 GB to avoid OOM on 4 GB Raspberry Pis.
# Sizes measured from the 20260329 planet file.
MAP_REGIONS = [
    # United States (split into 3 for Pi compatibility)
    {
        'name': 'United States (West)',
        'region': 'us-west',
        'bbox': '-125.0,24.4,-104.0,49.4',
        'size_estimate': 5 * GB,
    },
    {
        'name': 'United States (Central)',
        'region': 'us-central',
        'bbox': '-104.0,24.4,-87.0,49.4',
        'size_estimate': 5 * GB,
    },
    {
        'name': 'United States (East)',
        'region': 'us-east',
        'bbox': '-87.0,24.4,-66.9,49.4',
        'size_estimate': 8 * GB,
    },
    {
        'name': 'Alaska',
        'region': 'us-alaska',
        'bbox': '-180.0,51.0,-129.0,71.5',
        'size_estimate': int(1.4 * GB),
    },
    # Canada (split into 3)
    {
        'name': 'Canada (West)',
        'region': 'canada-west',
        'bbox': '-141.0,48.0,-110.0,83.5',
        'size_estimate': 5 * GB,
    },
    {
        'name': 'Canada (Central)',
        'region': 'canada-central',
        'bbox': '-110.0,48.0,-80.0,83.5',
        'size_estimate': 6 * GB,
    },
    {
        'name': 'Canada (East)',
        'region': 'canada-east',
        'bbox': '-80.0,41.7,-52.0,83.5',
        'size_estimate': 6 * GB,
    },
    {
        'name': 'Mexico',
        'region': 'mexico',
        'bbox': '-118.5,14.5,-86.7,32.8',
        'size_estimate': int(2.5 * GB),
    },
    # Central & South America
    {
        'name': 'Central America & Caribbean',
        'region': 'central-america',
        'bbox': '-92.2,7.2,-59.4,23.5',
        'size_estimate': int(1.4 * GB),
    },
    {
        'name': 'South America',
        'region': 'south-america',
        'bbox': '-81.4,-56.0,-34.7,12.5',
        'size_estimate': int(7.8 * GB),
    },
    # Europe (split into 9 grid boxes — dense OSM coverage requires small regions)
    {
        'name': 'Europe (NW: UK, Ireland, Iceland)',
        'region': 'europe-nw',
        'bbox': '-25.0,48.0,5.0,72.0',
        'size_estimate': int(5.5 * GB),
    },
    {
        'name': 'Europe (SW: Spain, Portugal)',
        'region': 'europe-sw',
        'bbox': '-25.0,34.0,5.0,48.0',
        'size_estimate': int(5.6 * GB),
    },
    {
        'name': 'Europe (N-Central: Scandinavia)',
        'region': 'europe-n-central',
        'bbox': '5.0,55.0,15.0,72.0',
        'size_estimate': int(3.6 * GB),
    },
    {
        'name': 'Europe (Central: Germany, Benelux)',
        'region': 'europe-central',
        'bbox': '5.0,48.0,15.0,55.0',
        'size_estimate': int(6.9 * GB),
    },
    {
        'name': 'Europe (S-Central: Italy, France)',
        'region': 'europe-s-central',
        'bbox': '5.0,34.0,15.0,48.0',
        'size_estimate': int(4.9 * GB),
    },
    {
        'name': 'Europe (NE-Central: Poland, Baltics)',
        'region': 'europe-ne-central',
        'bbox': '15.0,48.0,25.0,72.0',
        'size_estimate': int(7.2 * GB),
    },
    {
        'name': 'Europe (SE-Central: Balkans, Greece)',
        'region': 'europe-se-central',
        'bbox': '15.0,34.0,25.0,48.0',
        'size_estimate': int(3.2 * GB),
    },
    {
        'name': 'Europe (NE: Ukraine, Belarus)',
        'region': 'europe-ne',
        'bbox': '25.0,48.0,45.0,72.0',
        'size_estimate': int(7.4 * GB),
    },
    {
        'name': 'Europe (SE: Turkey, Black Sea)',
        'region': 'europe-se',
        'bbox': '25.0,34.0,45.0,48.0',
        'size_estimate': int(3.4 * GB),
    },
    # Africa (split into 2)
    {
        'name': 'Africa (North)',
        'region': 'africa-north',
        'bbox': '-18.0,0.0,52.0,37.5',
        'size_estimate': 9 * GB,
    },
    {
        'name': 'Africa (South)',
        'region': 'africa-south',
        'bbox': '-18.0,-35.0,52.0,0.0',
        'size_estimate': 5 * GB,
    },
    # Middle East
    {
        'name': 'Middle East',
        'region': 'middle-east',
        'bbox': '25.0,12.0,63.0,42.0',
        'size_estimate': int(4.1 * GB),
    },
    # Russia & Northern Asia (split into 3)
    {
        'name': 'Russia (West)',
        'region': 'russia-west',
        'bbox': '27.0,41.0,45.0,82.0',
        'size_estimate': 8 * GB,
    },
    {
        'name': 'Russia (Central)',
        'region': 'russia-central',
        'bbox': '45.0,41.0,100.0,82.0',
        'size_estimate': 3 * GB,
    },
    {
        'name': 'Russia (East)',
        'region': 'russia-east',
        'bbox': '100.0,41.0,180.0,82.0',
        'size_estimate': 4 * GB,
    },
    # South Asia
    {
        'name': 'South Asia',
        'region': 'south-asia',
        'bbox': '60.0,5.0,98.0,40.0',
        'size_estimate': int(5.5 * GB),
    },
    # East Asia (split into 2)
    {
        'name': 'East Asia (North)',
        'region': 'east-asia-north',
        'bbox': '73.0,35.0,150.0,53.5',
        'size_estimate': 6 * GB,
    },
    {
        'name': 'East Asia (South)',
        'region': 'east-asia-south',
        'bbox': '73.0,18.0,150.0,35.0',
        'size_estimate': 8 * GB,
    },
    # Southeast Asia
    {
        'name': 'Southeast Asia',
        'region': 'southeast-asia',
        'bbox': '92.0,-11.0,141.0,28.5',
        'size_estimate': 6 * GB,
    },
    # Oceania & Pacific
    {
        'name': 'Oceania & Australia',
        'region': 'oceania',
        'bbox': '110.0,-47.0,180.0,0.0',
        'size_estimate': int(3.7 * GB),
    },
    {
        'name': 'Pacific Islands',
        'region': 'pacific-islands',
        'bbox': '-180.0,-47.0,-120.0,28.5',
        'size_estimate': 88 * MB,
    },
    # Arctic & Antarctic
    {
        'name': 'Greenland',
        'region': 'greenland',
        'bbox': '-74.0,59.0,-10.0,84.0',
        'size_estimate': int(1.5 * GB),
    },
    {
        'name': 'Antarctica',
        'region': 'antarctica',
        'bbox': '-180.0,-90.0,180.0,-60.0',
        'size_estimate': 423 * MB,
    },
    # Terrain (DEM) — direct download, no bbox extraction.
    {
        'name': 'Terrain (Global Hillshade & Contours)',
        'region': 'terrain-z0-8',
        'bbox': None,
        'size_estimate': 12 * GB,
        'terrain': True,
    },
]

MAP_REGIONS_BY_NAME = {r['name']: r for r in MAP_REGIONS}
MAP_REGIONS_BY_REGION = {r['region']: r for r in MAP_REGIONS}
