"""Run bounded dispatch rounds without consuming publication obligations."""
import asyncio


async def run(service, stop):
    """Poll durable intent until stop is set; database failures retain pending work."""
    while not stop.is_set():
        try:
            await service.once()
        except Exception:
            # Never log adapter exceptions: Redis URLs may contain credentials.
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
        except TimeoutError:
            pass
