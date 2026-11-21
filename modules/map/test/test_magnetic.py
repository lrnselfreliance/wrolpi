import pytest

from modules.map import magnetic

# From the test values published with the model: year, altitude (km), latitude, longitude, declination, and the
# field north, east and down (nT).
TEST_VALUES = [
    (2025.0, 28, 89, -121, -99.77, -255.388723, -1482.460628, 56194.288771),
    (2025.0, 48, 80, -96, -29.91, 1875.982280, -1079.269389, 55623.044051),
    (2025.0, 54, 82, 87, 54.89, 1324.336929, 1883.428620, 56740.772059),
    (2025.0, 65, 43, 93, 0.50, 24299.852822, 210.517066, 50037.923998),
    (2025.0, 51, -33, 109, -5.49, 21737.778822, -2090.274098, -52710.003920),
    (2025.0, 39, -59, -8, -15.75, 14358.095523, -4049.107540, -24389.086374),
    (2025.0, 3, -50, -103, 27.96, 19526.532799, 10362.990980, -31437.562789),
    (2025.0, 94, -29, -110, 15.74, 23275.471080, 6559.046509, -19063.605287),
    (2025.0, 66, 14, 143, -0.19, 35003.441364, -116.624818, 7966.315182),
    (2025.0, 18, 0, 21, 1.29, 29274.811882, 659.800118, -14316.722540),
    (2025.5, 6, -36, -137, 20.28, 23781.930678, 8786.698927, -32577.518648),
    (2025.5, 63, 26, 81, 0.51, 34802.613433, 308.431881, 30332.056989),
]


def test_load_model():
    model = magnetic.load_model()
    assert (model.epoch, model.name, model.degree) == (2025.0, 'WMM-2025', 12)
    # Every harmonic of degrees 1 to 12.
    assert len(model.coefficients) == sum(n + 1 for n in range(1, 13))
    assert model.coefficients[0] == (1, 0, -29351.8, 0.0, 12.0, 0.0)
    assert model.coefficients[-1] == (12, 12, -0.7, 0.2, -0.1, -0.1)


@pytest.mark.parametrize('year,altitude,latitude,longitude,declination,north,east,down', TEST_VALUES)
def test_field(year, altitude, latitude, longitude, declination, north, east, down):
    """The field is what the model's own test values say it is."""
    model = magnetic.load_model()
    assert model.field(latitude, longitude, year, altitude) == pytest.approx((north, east, down), abs=0.01)
    assert model.declination(latitude, longitude, year, altitude) == pytest.approx(declination, abs=0.006)


def test_declination():
    """A compass in Anchorage points well east of north; in Maine, west."""
    assert 13 < magnetic.declination(61.19, -149.94, 2026.87) < 16
    assert -17 < magnetic.declination(45.0, -69.0, 2026.87) < -13


def test_declination_is_not_guessed():
    """There is no declination in a year the model is not of."""
    assert magnetic.declination(61.19, -149.94, 2024.99) is None
    assert magnetic.declination(61.19, -149.94, 2030.0) is None
    assert magnetic.declination(61.19, -149.94, 2029.99) is not None
