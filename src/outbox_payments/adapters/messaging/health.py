import asyncio

from faststream.rabbit import RabbitBroker


async def broker_is_reachable(url: str, *, within: float = 2.0) -> bool:
    """Open a short-lived AMQP connection. The API never publishes (the relay does),
    so it keeps no broker connection of its own."""
    broker = RabbitBroker(url, logger=None)
    try:
        async with asyncio.timeout(within):
            await broker.connect()
            return await broker.ping(timeout=within)
    except OSError, TimeoutError, ConnectionError:
        return False
    except Exception:  # noqa: BLE001 - aio-pika raises many types; any means "not ready"
        return False
    finally:
        await broker.stop()
