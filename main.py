import typer
import bellows.zigbee.application as bapp
from bellows.ezsp import EZSP
import bellows.types as t
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Iterable
from functools import reduce
from operator import ior


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
        (state,) = await ezsp.networkState()

        await ezsp.networkInit()

        await ezsp.startScan(
            t.EzspNetworkScanType.ACTIVE_SCAN,
            channel_mask([11]),
            3,
        )
