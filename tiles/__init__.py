"""The tile service: WROLPi's map as raster tiles, for apps which draw only those (ATAK, iTAK).

A service of its own (wrolpi-tiles), not part of the API: a phone taking an area offline asks for thousands of
tiles, each a few dozen milliseconds of CPU, and the API on a Raspberry Pi must stay responsive meanwhile.

Nothing here imports `wrolpi` or `modules`: importing them costs about a second and 130 MB, and every render
process would pay it.
"""
