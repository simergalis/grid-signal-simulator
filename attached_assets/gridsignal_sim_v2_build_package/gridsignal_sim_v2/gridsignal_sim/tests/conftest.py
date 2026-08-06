"""
tests/conftest.py — pytest session fixtures for the GridSignal test suite.

Responsibilities
----------------
1. Site-location singleton reset.
   api/app.py's lifespan reads gridsignal_site.json and calls set_site_location()
   on every TestClient construction.  This persists across tests because
   site_config._stored is a process-level module variable.  A test that relies
   on the default location (e.g. test_solar_weather_propagation) fails after any
   TestClient test that ran with a non-default location already stored in
   gridsignal_site.json.

   Fix: capture _stored before each test, restore it after, regardless of what
   the test or its fixtures write to the singleton.

   This fixture is autouse=True so it wraps every test without annotation.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_site_location_singleton():
    """Save and restore the site_config process-level singleton around every test.

    Prevents TestClient lifespans that call set_site_location() (triggered by
    gridsignal_site.json load in api/app.py) from contaminating the location seen
    by subsequent tests.
    """
    import site_config as _sc
    _before = _sc._stored          # save (may be None on the first test)
    yield
    _sc._stored = _before          # restore — regardless of what the test wrote
