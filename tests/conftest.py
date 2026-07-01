"""Pytest configuration for the LinkTap integration tests."""

import pytest
import pytest_socket

pytest_plugins = "pytest_homeassistant_custom_component"

# pytest-homeassistant-custom-component disables sockets in its per-test
# ``pytest_runtest_setup``, allowing only unix sockets for asyncio's self-pipe.
# On Windows asyncio builds the event loop self-pipe with an AF_INET
# ``socket.socketpair()``, which is blocked at creation, so the loop cannot be
# built and every test errors. Neutralise the disable here (it is referenced via
# the module attribute at call time). Tests mock the gateway client and use no
# real network, so this is safe.
pytest_socket.disable_socket = lambda *args, **kwargs: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield
