# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from copy import deepcopy

import pytest
from selenium.webdriver import Safari

from utils import factory


@pytest.fixture
def safari_driver(capabilities, driver_path):
    """Return a factory function creating Chrome WebDriver instances.
    """
    @factory
    def _get_instance():
        """Return Chrome WebDriver instance based on given options.
        """
        kwargs = {}
        if capabilities:
            kwargs['desired_capabilities'] = deepcopy(capabilities)
        if driver_path:
            kwargs['executable_path'] = driver_path
        return Safari(**kwargs)
    return _get_instance
