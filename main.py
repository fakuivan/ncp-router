import typer
import bellows.zigbee.application as bapp
from bellows.ezsp import EZSP
import bellows.types as t
import bellows.zigbee.util
from zigpy.state import NetworkInfo
from contextlib import asynccontextmanager, contextmanager
from collections.abc import AsyncIterator, Iterable, Iterator
from functools import reduce
from operator import ior
from asyncio import Future


def channel_mask(channels: Iterable[int]) -> int:
    return reduce(ior, (1 << channel for channel in channels), 0)


def join():
    bapp.ControllerApplication.SCHEMA


@asynccontextmanager
async def ezsp_connect(ezsp: EZSP, *, use_thread: bool = True) -> AsyncIterator[EZSP]:
    await ezsp.connect(use_thread=use_thread)
    try:
        yield ezsp
    finally:
        ezsp.close()


async def main():
    schema = bapp.ControllerApplication.SCHEMA(
        {"device": {"path": "socket://172.31.112.103:8888"}}
    )

    async with ezsp_connect(EZSP(schema["device"])) as ezsp:
        await ezsp.startup_reset()
        await ezsp.write_config(schema["ezsp_config"])
        print(await ezsp.networkState())

        print(await ezsp.networkInit())
        print(await ezsp.setInitialSecurityState(default_initial_security_state()))

        nets = await ezsp.startScan(
            t.EzspNetworkScanType.ACTIVE_SCAN, channel_mask([11]), 3
        )
        print(nets)

        ((best_net, _), *_) = sorted(
            [(res, rssi) for res, lqi, rssi in nets if res.allowingJoin],
            key=lambda entry: -entry[1],
        )
        print(best_net)

        assert isinstance(best_net, t.EmberZigbeeNetwork)

        print(
            await joinNetwork(
                ezsp,
                t.EmberNodeType.ROUTER,
                with_default_net_params(scan_result_to_params(best_net)),
            )
        )
        input("Press enter to disconnect from EZSP")


def scan_result_to_params(net: t.EmberZigbeeNetwork) -> t.EmberNetworkParameters:
    params = t.EmberNetworkParameters()
    params.extendedPanId = net.extendedPanId
    params.panId = net.panId
    params.radioChannel = net.channel
    params.nwkUpdateId = net.nwkUpdateId
    return params


def with_default_net_params(net: t.EmberNetworkParameters) -> t.EmberNetworkParameters:
    net = t.EmberNetworkParameters(net)
    net.radioTxPower = t.uint8_t(8)
    net.joinMethod = t.EmberJoinMethod.USE_MAC_ASSOCIATION
    net.channels = t.uint32_t(0)
    net.nwkManagerId = t.uint32_t(0)
    return net


def default_initial_security_state():
    return bellows.zigbee.util.zha_security(
        network_info=NetworkInfo(), use_hashed_tclk=False
    )


async def joinNetwork(
    ezsp: EZSP, node_type: t.EmberNodeType, net_params: t.EmberNetworkParameters
) -> t.EmberStatus:
    with wait_for_any_stack_status(ezsp) as net_join_status:
        (status,) = await ezsp.joinNetwork(node_type, net_params)
        assert isinstance(status, t.EmberStatus)
        if status != t.EmberStatus.SUCCESS:
            return status
        return await net_join_status


@contextmanager
def wait_for_any_stack_status(ezsp: EZSP) -> Iterator[Future[t.EmberStatus]]:
    fut = Future()

    def callback(frame_name: str, response):
        if frame_name == "stackStatusHandler":
            (status,) = response
            fut.set_result(status)

    fut.add_done_callback(lambda _: ezsp.remove_callback(callback_id))

    callback_id = ezsp.add_callback(callback)
    try:
        yield fut
    finally:
        # Cancel since we're going outside the scope of the with block
        fut.cancel()
