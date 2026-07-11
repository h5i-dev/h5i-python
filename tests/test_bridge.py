import asyncio

import pytest

from h5i.orchestra import BridgeClosedError, H5iError, ProtocolError, RpcError
from mock_server import MockError, MockOrchestra, connect


async def test_concurrent_requests_multiplex_out_of_order():
    mock = MockOrchestra()
    release = asyncio.Event()

    async def slow(_params):
        await release.wait()
        return "slow-done"

    mock.on("slow", slow)
    mock.on("fast", lambda p: "fast-done")
    bridge, server = connect(mock)
    try:
        slow_future = asyncio.ensure_future(bridge.request("slow", {}))
        fast_result = await bridge.request("fast", {})
        assert fast_result == "fast-done"  # answered while `slow` is in flight
        assert not slow_future.done()
        release.set()
        assert await slow_future == "slow-done"
    finally:
        await bridge.notify_close()
        server.cancel()


async def test_error_mapping_to_typed_exceptions():
    mock = MockOrchestra()

    def boom(_params):
        raise MockError("orchestra: concurrent steps under one label", kind="metadata")

    mock.on("bad", boom)
    bridge, server = connect(mock)
    try:
        with pytest.raises(H5iError) as excinfo:
            await bridge.request("bad", {})
        assert excinfo.value.kind == "metadata"
        assert "concurrent steps" in str(excinfo.value)

        with pytest.raises(RpcError) as excinfo:
            await bridge.request("definitely.unknown", {})
        assert excinfo.value.code == -32601
        assert not isinstance(excinfo.value, H5iError)
    finally:
        await bridge.notify_close()
        server.cancel()


async def test_server_death_fails_inflight_requests():
    mock = MockOrchestra()

    def die(_params):
        assert mock._writer is not None
        mock._writer.close()  # EOF mid-request, no response

    mock.on("die", die)
    bridge, server = connect(mock)
    try:
        with pytest.raises(BridgeClosedError) as excinfo:
            await bridge.request("die", {})
        assert "resumes" in str(excinfo.value)  # points the user at durability
        # And later requests fail fast with the same story.
        with pytest.raises(BridgeClosedError):
            await bridge.request("anything", {})
    finally:
        await bridge.notify_close()
        server.cancel()


async def test_non_json_on_stdout_is_a_protocol_error():
    mock = MockOrchestra()

    def garbage(_params):
        assert mock._writer is not None
        mock._writer.write(b"warning: something printed to stdout\n")

    mock.on("garbage", garbage)
    bridge, server = connect(mock)
    try:
        with pytest.raises(ProtocolError) as excinfo:
            await bridge.request("garbage", {})
        assert "stdout" in str(excinfo.value)
    finally:
        await bridge.notify_close()
        server.cancel()
