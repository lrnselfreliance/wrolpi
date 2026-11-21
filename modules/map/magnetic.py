"""Where a compass points: the World Magnetic Model.

A compass does not point at the north a map is drawn to, and how far off it is depends on where it is and when.
The model is the Earth's magnetic field as a sum of spherical harmonics, each of which changes at a steady rate
for the five years the model is good for.

`wmm/WMM2025.COF` is the coefficient file of the World Magnetic Model 2025, as it is published by the NOAA
National Centers for Environmental Information and the British Geological Survey
(https://www.ncei.noaa.gov/products/world-magnetic-model).  It is a work of the U.S. Government, in the public
domain.  It is good from 2025.0 until 2030.0, when its successor is published: put that file beside it, and name
it in MODEL_PATH.
"""
import math
import pathlib
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

__all__ = ['MagneticModel', 'load_model', 'declination', 'MODEL_PATH']

MODEL_PATH = pathlib.Path(__file__).parent / 'wmm' / 'WMM2025.COF'
# How many years a model is good for, from its epoch.
MODEL_YEARS = 5

# The WGS 84 ellipsoid (kilometers), and the radius of the sphere the model is of.
WGS84_A = 6378.137
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
MODEL_RADIUS = 6371.2


@dataclass
class MagneticModel:
    # The decimal year the coefficients are of.
    epoch: float
    name: str
    # (n, m, g, h, the change of g in a year, the change of h in a year): nanoteslas.
    coefficients: List[Tuple[int, int, float, float, float, float]]

    @property
    def degree(self) -> int:
        return max(i[0] for i in self.coefficients)

    def covers(self, year: float) -> bool:
        return self.epoch <= year < self.epoch + MODEL_YEARS

    def field(self, latitude: float, longitude: float, year: float,
              altitude: float = 0) -> Tuple[float, float, float]:
        """The magnetic field (nanoteslas north, east and down) at a place (degrees of WGS 84; `altitude` is
        kilometers above the ellipsoid) in a decimal year."""
        phi, lam = math.radians(latitude), math.radians(longitude)
        # The place as the sphere has it: how far from the center of the Earth, and at what angle from its axis.
        curvature = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(phi) ** 2)
        p = (curvature + altitude) * math.cos(phi)
        z = (curvature * (1 - WGS84_E2) + altitude) * math.sin(phi)
        r = math.hypot(p, z)
        geocentric = math.asin(z / r)
        cos_t, sin_t = math.sin(geocentric), math.cos(geocentric)

        # The Schmidt semi-normalized Legendre functions of the angle from the axis, and their derivatives.
        size = self.degree + 1
        legendre = [[0.0] * size for _ in range(size)]
        derivative = [[0.0] * size for _ in range(size)]
        legendre[0][0] = 1.0
        for n in range(1, size):
            for m in range(n + 1):
                if n == m:
                    k = 1.0 if n == 1 else math.sqrt((2 * n - 1) / (2 * n))
                    legendre[n][n] = k * sin_t * legendre[n - 1][n - 1]
                    derivative[n][n] = k * (sin_t * derivative[n - 1][n - 1] + cos_t * legendre[n - 1][n - 1])
                else:
                    k = math.sqrt(n * n - m * m)
                    before = math.sqrt((n - 1) ** 2 - m * m) if n > 1 and m <= n - 2 else 0.0
                    legendre[n][m] = ((2 * n - 1) * cos_t * legendre[n - 1][m]
                                      - before * (legendre[n - 2][m] if n > 1 else 0.0)) / k
                    derivative[n][m] = ((2 * n - 1) * (cos_t * derivative[n - 1][m] - sin_t * legendre[n - 1][m])
                                        - before * (derivative[n - 2][m] if n > 1 else 0.0)) / k

        years = year - self.epoch
        north = east = down = 0.0
        for n, m, g, h, g_rate, h_rate in self.coefficients:
            g, h = g + years * g_rate, h + years * h_rate
            ratio = (MODEL_RADIUS / r) ** (n + 2)
            cos_m, sin_m = math.cos(m * lam), math.sin(m * lam)
            north += ratio * (g * cos_m + h * sin_m) * derivative[n][m]
            east += ratio * m * (g * sin_m - h * cos_m) * legendre[n][m] / sin_t
            down -= ratio * (n + 1) * (g * cos_m + h * sin_m) * legendre[n][m]

        # From the sphere's north and down to the ellipsoid's.
        turn = geocentric - phi
        return (north * math.cos(turn) - down * math.sin(turn), east,
                north * math.sin(turn) + down * math.cos(turn))

    def declination(self, latitude: float, longitude: float, year: float, altitude: float = 0) -> float:
        """How far east of true north (degrees) a compass points at a place in a decimal year."""
        north, east, _ = self.field(latitude, longitude, year, altitude)
        return math.degrees(math.atan2(east, north))


@lru_cache(maxsize=None)
def load_model(path: pathlib.Path = MODEL_PATH) -> MagneticModel:
    """Read a model's coefficient file: a line of its epoch and name, then a line for each harmonic."""
    lines = path.read_text().splitlines()
    epoch, name = lines[0].split()[:2]
    coefficients = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 6:
            # The lines of nines which end the file.
            continue
        coefficients.append((int(parts[0]), int(parts[1]), *(float(i) for i in parts[2:])))
    return MagneticModel(epoch=float(epoch), name=name, coefficients=coefficients)


def declination(latitude: float, longitude: float, year: float) -> Optional[float]:
    """How far east of true north (degrees) a compass points at a place on the ground in a decimal year, or None
    in a year the model is not of: it is not known, and a guess is worse than nothing."""
    model = load_model()
    if not model.covers(year):
        return None
    return model.declination(latitude, longitude, year)
