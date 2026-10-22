import asyncio
from types import SimpleNamespace

import pytest

from serve import check_service_exits


def test_unexpected_normal_service_return_is_failure():
    async def scenario():
        completed=asyncio.get_running_loop().create_future();completed.set_result(None)
        other=asyncio.get_running_loop().create_future()
        with pytest.raises(RuntimeError,match='stopped unexpectedly'):
            check_service_exits([SimpleNamespace(should_exit=False),SimpleNamespace(should_exit=False)],[completed,other])
    asyncio.run(scenario())


def test_requested_shutdown_is_success_but_service_exception_is_failure():
    async def scenario():
        completed=asyncio.get_running_loop().create_future();completed.set_result(None)
        check_service_exits([SimpleNamespace(should_exit=True)],[completed])
        error=asyncio.get_running_loop().create_future();error.set_exception(ValueError('Service failed'))
        with pytest.raises(RuntimeError,match='stopped unexpectedly') as exc:
            check_service_exits([SimpleNamespace(should_exit=True)],[error])
        assert isinstance(exc.value.__cause__,ValueError)
    asyncio.run(scenario())


def test_unexpected_cancellation_fails_without_leaking_cancelled_error():
    async def scenario():
        cancelled=asyncio.get_running_loop().create_future();cancelled.cancel()
        with pytest.raises(RuntimeError,match='stopped unexpectedly'):
            check_service_exits([SimpleNamespace(should_exit=False)],[cancelled])
        check_service_exits([SimpleNamespace(should_exit=True)],[cancelled])
    asyncio.run(scenario())
