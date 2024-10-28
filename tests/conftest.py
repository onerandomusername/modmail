import os
from typing import TYPE_CHECKING

import aiohttp
import aioresponses
import pytest


if TYPE_CHECKING:
    from _pytest.reports import TestReport
# Reference:
# https://docs.pytest.org/en/latest/writing_plugins.html#hookwrapper-executing-around-other-hooks
# https://docs.pytest.org/en/latest/writing_plugins.html#hook-function-ordering-call-example
# https://docs.pytest.org/en/stable/reference.html#pytest.hookspec.pytest_runtest_makereport
#
# Inspired by:
# https://github.com/pytest-dev/pytest/blob/master/src/_pytest/terminal.py


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report: "TestReport"):
    """Add annotations of test failures or xpassed to github actions."""
    # enable only in a workflow of GitHub Actions
    if os.environ.get("GITHUB_ACTIONS") is None:
        return

    if not report.when == "call":
        return

    skip = not report.failed
    message = "Test Failure."
    if hasattr(report, "wasxfail") and report.outcome == "passed":
        skip = False
        message = "Unexpected test success."

    if skip:
        return

    print(
        "\n::error file={location[0]},line={location[1]},title={location[2]}::{message}".format(
            location=report.location, message=message
        )
    )


@pytest.fixture
def aioresponse():
    """Fixture to mock aiohttp responses."""
    with aioresponses.aioresponses() as aioresponse:
        yield aioresponse


@pytest.fixture
@pytest.mark.asyncio
async def http_session(aioresponse) -> aiohttp.ClientSession:
    """
    Fixture function for a aiohttp.ClientSession.

    Requests fixture aioresponse to ensure that all client sessions do not make actual requests.
    """
    resolver = aiohttp.AsyncResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    client_session = aiohttp.ClientSession(connector=connector)

    yield client_session

    await client_session.close()
    await connector.close()
    await resolver.close()
