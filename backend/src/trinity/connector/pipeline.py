"""Fixed-window extraction for all routes; candidate preparation comes later."""

from collections.abc import Callable
from datetime import date

import httpx

from trinity.config import ConfigurationError, EIASettings
from trinity.connector.client import EIAClient, EIAClientError, EIAInputError, EIARetrievalCancelled
from trinity.connector.retrieval import RetrievalResult


DATASETS = ("national", "facility", "generator")


async def retrieve_all(
    *, start: date, end: date, page_size: int = 5000, max_pages: int = 1000,
    timeout_seconds: float = 300.0,
    on_result: Callable[[RetrievalResult], None] | None = None,
    settings: EIASettings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[RetrievalResult]:
    """One pool, sequential routes, one final result per route on normal failure.

    A failed route does not stop the other routes. Cancellation records the
    interrupted route and skipped routes, then propagates. A sink failure
    propagates immediately, since saved evidence cannot then be guaranteed.
    """
    results: list[RetrievalResult] = []

    def emit(result: RetrievalResult) -> None:
        results.append(result)
        if on_result is not None:
            on_result(result)

    try:
        client = EIAClient(settings, transport=transport)
    except ConfigurationError:
        for dataset in DATASETS:
            tracker = EIAClient.retrieval_tracker(dataset, start, end)
            emit(RetrievalResult(tracker.finish(
                "failed", error_code="configuration_error",
                error_message="Set EIA_API_KEY to a non-empty value in the process environment.",
            )))
        return results

    async with client:
        for index, dataset in enumerate(DATASETS):
            try:
                collection = await getattr(client, f"fetch_{dataset}")(
                    start=start, end=end, page_size=page_size,
                    max_pages=max_pages, timeout_seconds=timeout_seconds,
                )
            except (EIAClientError, EIAInputError) as error:
                assert error.metadata is not None
                result = RetrievalResult(error.metadata)
            except EIARetrievalCancelled as error:
                emit(RetrievalResult(error.metadata))
                for remaining in DATASETS[index + 1:]:
                    tracker = EIAClient.retrieval_tracker(remaining, start, end)
                    emit(RetrievalResult(tracker.finish(
                        "skipped", error_code="cancelled_before_start",
                        error_message="Not started because extraction was cancelled.",
                    )))
                raise
            else:
                assert collection.metadata is not None
                result = RetrievalResult(collection.metadata, collection)
            emit(result)
    return results
