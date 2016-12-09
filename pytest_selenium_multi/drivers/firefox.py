# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from copy import deepcopy

import pytest
from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary

from utils import factory


def pytest_addoption(parser):
    group = parser.getgroup('selenium', 'selenium')
    group._addoption('--firefox-path',
                     metavar='path',
                     help='path to the firefox binary.')
    group._addoption('--firefox-preference',
                     action='append',
                     default=[],
                     dest='firefox_preferences',
                     metavar=('name', 'value'),
                     nargs=2,
                     help='additional firefox preferences.')
    group._addoption('--firefox-profile',
                     metavar='path',
                     help='path to the firefox profile.')
    group._addoption('--firefox-extension',
                     action='append',
                     default=[],
                     dest='firefox_extensions',
                     metavar='path',
                     help='path to a firefox extension.')
    group._addoption('--firefox-logs',
                     help="catch console logs",
                     dest='enable_logs',
                     action='store_true')


@pytest.fixture
def firefox_driver(capabilities, driver_path, firefox_profile,
                   firefox_path, firefox_timeout):
    """Return a factory function creating Firefox WebDriver instances.
    """
    @factory
    def _get_instance():
        """Return Firefox WebDriver instance based on given options.
        """
        kwargs = {'timeout': firefox_timeout}
        if capabilities:
            kwargs['capabilities'] = deepcopy(capabilities)
        if driver_path:
            kwargs['executable_path'] = driver_path
        if firefox_path:
            # get firefox binary from options until there's capabilities support
            kwargs['firefox_binary'] = FirefoxBinary(firefox_path)
        kwargs['firefox_profile'] = firefox_profile.get_instance()
        return Firefox(**kwargs)
    return _get_instance


@pytest.fixture(scope='session')
def firefox_timeout():
    return 120


@pytest.fixture(scope='session')
def firefox_path(request):
    return request.config.getoption('firefox_path')


@pytest.fixture
def firefox_profile(request):
    """Return a factory function creating Firefox profile instances.
    """
    @factory
    def _get_instance():
        """Return Firefox profile instance based on given options.
        """
        profile = FirefoxProfile(request.config.getoption('firefox_profile'))
        for preference in request.config.getoption('firefox_preferences'):
            name, value = preference
            if value.isdigit():
                # handle integer preferences
                value = int(value)
            elif value.lower() in ['true', 'false']:
                # handle boolean preferences
                value = value.lower() == 'true'
            profile.set_preference(name, value)
        profile.update_preferences()
        for extension in request.config.getoption('firefox_extensions'):
            profile.add_extension(extension)
        return profile
    return _get_instance
