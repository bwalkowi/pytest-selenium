# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
from datetime import datetime
import re
import os
import sys
import time

from selenium.webdriver.support.event_firing_webdriver import \
    EventFiringWebDriver

from drivers.utils import factory

import pytest


RE_LOG = re.compile(r'<log>.*?</log>')
RE_LOG_MSG = re.compile(r'<log>'
                        r'<class>(?P<class>.*?)</class>'
                        r'(<cat>(?P<cat>.*?)</cat>)?'
                        r'<msg>(?P<msg>.*?)</msg>.*?'
                        r'</log>')


PY3 = sys.version_info[0] == 3

SUPPORTED_DRIVERS = [
    'BrowserStack',
    'Chrome',
    'Firefox',
    'IE',
    'PhantomJS',
    'Remote',
    'SauceLabs',
    'TestingBot']


def pytest_addhooks(pluginmanager):
    from . import hooks
    method = getattr(pluginmanager, 'add_hookspecs', None)
    if method is None:
        method = pluginmanager.addhooks
    method(hooks)


@pytest.fixture(scope='session', autouse=True)
def _environment(request, session_capabilities):
    """Provide additional environment details to pytest-html report"""
    config = request.config
    # add environment details to the pytest-html plugin
    config._environment.append(('Driver', config.option.driver))
    # add capabilities to environment
    config._environment.extend([('Capability', '{0}: {1}'.format(
        k, v)) for k, v in session_capabilities.items()])
    if config.option.driver == 'Remote':
        config._environment.append(
            ('Server', 'http://{0.host}:{0.port}'.format(config.option)))


@pytest.fixture(scope='session')
def session_capabilities(request, variables):
    """Returns combined capabilities from pytest-variables and command line"""
    capabilities = variables.get('capabilities', {})
    for capability in request.config.getoption('capabilities'):
        capabilities[capability[0]] = capability[1]
    return capabilities


@pytest.fixture
def capabilities(request, session_capabilities):
    """Returns combined capabilities"""
    capabilities = copy.deepcopy(session_capabilities)  # make a copy
    capabilities_marker = request.node.get_marker('capabilities')
    if capabilities_marker is not None:
        # add capabilities from the marker
        capabilities.update(capabilities_marker.kwargs)
    return capabilities


@pytest.fixture
def driver_path(request):
    return request.config.getoption('driver_path')


@pytest.fixture
def driver(request):
    """Return a factory function creating WebDriver instances.
    """
    driver_type = request.config.getoption('driver')
    if driver_type is None:
        raise pytest.UsageError('--driver must be specified')

    driver_fixture = '{0}_driver'.format(driver_type.lower())
    driver_factory = request.getfuncargvalue(driver_fixture)

    event_listener = request.config.getoption('event_listener')
    if event_listener:
        # Import the specified event listener and wrap the driver instance
        mod_name, class_name = event_listener.rsplit('.', 1)
        mod = __import__(mod_name, fromlist=[class_name])
        event_listener = getattr(mod, class_name)

    @factory
    def _get_instance():
        """Return WebDriver instance based on given options.
        """
        web_driver = driver_factory.get_instance()
        if event_listener and not isinstance(web_driver, EventFiringWebDriver):
            web_driver = EventFiringWebDriver(web_driver, event_listener())

        request.node._driver = web_driver
        request.addfinalizer(web_driver.quit)
        return web_driver
    return _get_instance


@pytest.fixture
def config_driver():
    def _configure(driver):
        return driver
    return _configure


def select_browser(selenium, browser_id):
    browser = selenium[browser_id]
    selenium['request'].node._driver = browser
    return browser


@pytest.fixture
def selenium(request):
    """Returns a WebDriver instance based on options and capabilities"""
    return {'request': request}


def pytest_configure(config):
    if hasattr(config, 'slaveinput'):
        return  # xdist slave
    config.addinivalue_line(
        'markers', 'capabilities(kwargs): add or change existing '
        'capabilities. specify capabilities as keyword arguments, for example '
        'capabilities(foo=''bar'')')


def pytest_report_header(config, startdir):
    driver = config.getoption('driver')
    if driver is not None:
        return 'driver: {0}'.format(driver)


@pytest.mark.hookwrapper
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    summary = []
    extra = getattr(report, 'extra', [])
    driver = getattr(item, '_driver', None)
    xfail = hasattr(report, 'wasxfail')
    xvfb_rec = item.config.option.xvfb_recording
    failure = (report.skipped and xfail) or (report.failed and not xfail)
    when = item.config.getini('selenium_capture_debug').lower()
    capture_debug = when == 'always' or (when == 'failure' and failure)
    if driver is not None:
        if capture_debug:
            exclude = item.config.getini('selenium_exclude_debug').lower()
            if 'url' not in exclude:
                _gather_url(item, report, driver, summary, extra)
            if 'screenshot' not in exclude:
                _gather_screenshot(item, report, driver, summary, extra)
            if 'html' not in exclude:
                _gather_html(item, report, driver, summary, extra)
            if 'logs' not in exclude:
                _gather_logs(item, report, driver, summary, extra)
            item.config.hook.pytest_selenium_capture_debug(
                item=item, report=report, extra=extra)
        if xvfb_rec and not failure:
            movie_name = '{name}.mp4'.format(name=item.name)
            logdir = os.path.dirname(item.config.option.htmlpath)
            movie_path = os.path.join(logdir, 'movies', movie_name)
            if os.path.isfile(movie_path):
                os.remove(movie_path)

        item.config.hook.pytest_selenium_runtest_makereport(
            item=item, report=report, summary=summary, extra=extra)
    if summary:
        report.sections.append(('pytest-selenium', '\n'.join(summary)))
    report.extra = extra


def _gather_url(item, report, driver, summary, extra):
    try:
        url = driver.current_url
    except Exception as e:
        summary.append('WARNING: Failed to gather URL: {0}'.format(e))
        return
    pytest_html = item.config.pluginmanager.getplugin('html')
    if pytest_html is not None:
        # add url to the html report
        extra.append(pytest_html.extras.url(url))
    summary.append('URL: {0}'.format(url))


def _gather_screenshot(item, report, driver, summary, extra):
    try:
        screenshot = driver.get_screenshot_as_base64()
    except Exception as e:
        summary.append('WARNING: Failed to gather screenshot: {0}'.format(e))
        return
    pytest_html = item.config.pluginmanager.getplugin('html')
    if pytest_html is not None:
        # add screenshot to the html report
        extra.append(pytest_html.extras.image(screenshot, 'Screenshot'))


def _gather_html(item, report, driver, summary, extra):
    try:
        html = driver.page_source
        if not PY3:
            html = html.encode('utf-8')
    except Exception as e:
        summary.append('WARNING: Failed to gather HTML: {0}'.format(e))
        return
    pytest_html = item.config.pluginmanager.getplugin('html')
    if pytest_html is not None:
        # add page source to the html report
        extra.append(pytest_html.extras.text(html, 'HTML'))


def _gather_logs(item, report, driver, summary, extra):
    try:
        types = driver.log_types
    except Exception as e:
        # note that some drivers may not implement log types
        summary.append('WARNING: Failed to gather log types: {0}'.format(e))
        return
    for name in types:
        try:
            log = driver.get_log(name)
        except Exception as e:
            summary.append('WARNING: Failed to gather {0} log: {1}'.format(
                name, e))
            return
        pytest_html = item.config.pluginmanager.getplugin('html')

        # driver.get_log(name) is bugged for firefox, so instead logs are written
        # to file using consoleExport and firebug, so we read it, parse to json,
        # format and append to end of logs
        formatted_logs = ''
        if driver.logs_enabled:
            console_logs = []
            with open(os.path.join(driver.root_dir,
                                   driver.instance_name,
                                   'logs', 'firefox.log')) as f:
                logs = ''.join(f.readlines())

            for console_log in RE_LOG.finditer(logs):
                log_info = RE_LOG_MSG.match(console_log.group(0))
                if log_info:
                    level = log_info.group('class')
                    cat = log_info.group('cat')
                    if cat and (cat.upper() in level.upper()):
                        level = cat
                    msg = log_info.group('msg')

                    formatted_log = {'timestamp': time.time() * 1000,
                                     'message': msg,
                                     'source': 'console-api',
                                     'level': level.upper()}
                    console_logs.append(formatted_log)
            formatted_logs = '\n\n\n\n{0}\n\nCONSOLE LOGS:\n\n{0}\n\n\n\n{1}' \
                             ''.format('='*180, format_log(console_logs))

        if pytest_html is not None:
            extra.append(pytest_html.extras.text(
                '{}{}'.format(format_log(log), formatted_logs),
                '%s Log' % name.title()))


def format_log(log):
    timestamp_format = '%Y-%m-%d %H:%M:%S.%f'
    entries = [u'{0} {1[level]} - {1[message]}'.format(
        datetime.utcfromtimestamp(entry['timestamp'] / 1000.0).strftime(
            timestamp_format), entry).rstrip() for entry in log]
    log = '\n'.join(entries)
    if not PY3:
        log = log.encode('utf-8')
    return log


def split_class_and_test_names(nodeid):
    """Returns the class and method name from the current test"""
    names = nodeid.split('::')
    names[0] = names[0].replace('/', '.')
    names = [x.replace('.py', '') for x in names if x != '()']
    classnames = names[:-1]
    classname = '.'.join(classnames)
    name = names[-1]
    return (classname, name)


def pytest_addoption(parser):
    _capture_choices = ('never', 'failure', 'always')
    parser.addini('selenium_capture_debug',
                  help='when debug is captured {0}'.format(_capture_choices),
                  default=os.getenv('SELENIUM_CAPTURE_DEBUG', 'failure'))
    parser.addini('selenium_exclude_debug',
                  help='debug to exclude from capture',
                  default=os.getenv('SELENIUM_EXCLUDE_DEBUG'))

    group = parser.getgroup('selenium', 'selenium')
    group._addoption('--driver',
                     choices=SUPPORTED_DRIVERS,
                     help='webdriver implementation.',
                     metavar='str')
    group._addoption('--xvfb-recording',
                     help='record tests using ffmpeg '
                          'and save results to <logdir>/movies/',
                     dest='xvfb_recording',
                     action='store_true')
    group._addoption('--driver-path',
                     metavar='path',
                     help='path to the driver executable.')
    group._addoption('--capability',
                     action='append',
                     default=[],
                     dest='capabilities',
                     metavar=('key', 'value'),
                     nargs=2,
                     help='additional capabilities.')
    group._addoption('--event-listener',
                     metavar='str',
                     help='selenium eventlistener class, e.g. '
                          'package.module.EventListenerClassName.')
