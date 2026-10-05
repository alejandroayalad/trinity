"""Reconcile lost refresh notifications without creating another run."""
import asyncio


async def run(dispatch, stop):
    """Poll committed intent; dependency failures retain durable pending work."""
    while not stop.is_set():
        try:
            await dispatch.recover()
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except TimeoutError:
            pass
