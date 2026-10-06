"""Reuse complete evidence verification with bounded, request-owned single-flight.

An authorized execution supplies its pinned publication, trusted namespace and
original deadline. Concurrent callers for that identity share one verification.
Only immutable safe diagnostic summaries survive success; projection creates
new models for the requested dataset. This module grants no data permissions.

The first caller performs the work synchronously and retains its query slot and
reader until it stops. Other callers wait without holding the cache lock. Their
cancellation cannot close the owner's reader. No detached background fill can
outlive the owner or extend the original analytical budget.
"""

from collections import OrderedDict
from dataclasses import dataclass, field, fields
import threading
import time

from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import canonical_json
from trinity.errors import Problem
from trinity.publication.diagnostics import project_diagnostics, read_verified_diagnostics

MAX_ENTRIES = 16
TTL_SECONDS = 60
WAIT_SECONDS = 0.05


@dataclass
class _Entry:
    """Hold one shared fill, then its immutable success until fixed expiry."""

    end: float
    callers: dict = field(default_factory=dict)
    done: bool = False
    abandoned: bool = False
    summaries: tuple = ()
    failure: tuple | None = None
    expires_at: float = 0


class _FillDeadline:
    """Stop when the fill budget ends or nobody still needs its result."""

    def __init__(self, entry, condition, clock):
        self.entry, self.condition, self.clock = entry, condition, clock

    def remaining(self):
        """Use live demand without extending the initiating request's budget."""
        with self.condition:
            left = self.entry.end - self.clock()
            if self.entry.abandoned or left <= 0:
                raise Problem(504, 'query_timeout')
            remaining = []
            for deadline in self.entry.callers.values():
                try:
                    remaining.append(deadline.remaining())
                except Problem:
                    # A disconnected or expired caller is not demand. The owner
                    # can still serve another live caller before its fixed end.
                    continue
            if not remaining:
                self.entry.abandoned = True
                raise Problem(504, 'query_timeout')
            return min(left, max(remaining))


class EvidenceCache:
    """Keep bounded per-process evidence identities; never cache authority or rows."""

    def __init__(self, *, max_entries=MAX_ENTRIES, ttl_seconds=TTL_SECONDS, clock=time.monotonic):
        """Start empty with trusted bounds and a monotonic clock for fixed expiry."""
        if type(max_entries) is not int or max_entries < 1 or ttl_seconds <= 0:
            raise ValueError('Invalid evidence cache bounds')
        self.max_entries, self.ttl_seconds, self.clock = max_entries, ttl_seconds, clock
        self._condition = threading.Condition()
        self._entries = OrderedDict()

    def _key(self, pinned, namespace):
        """Bind all pinned fields, including type distinctions, to trusted storage.

        Canonical bytes distinguish a boolean from an integer. Include every
        dataclass field so a new evidence binding cannot silently miss the key.
        The namespace comes from deployment configuration, never HTTP input.
        """
        binding = {item.name: getattr(pinned, item.name) for item in fields(pinned)
                   if item.name != 'publication'}
        binding['publication'] = pinned.publication.model_dump(mode='json')
        return tuple(namespace), canonical_json(binding)

    def read(self, pinned, dataset, reader, deadline, *, namespace):
        """Join or own a bounded fill and return only the authorized dataset.

        Admission and authorization must already have succeeded. A hit still
        checks the caller's deadline. Failures wake current waiters but leave no
        cache entry; the next independent request may attempt verification.
        """
        deadline.remaining()
        if dataset not in DATASETS:
            raise Problem(503, 'dependency_unavailable')
        key = self._key(pinned, namespace)
        caller = object()
        owner = False
        with self._condition:
            while True:
                left = deadline.remaining()
                now = self.clock()
                # Expiry is measured from successful verification, never from
                # the last hit. Pending entries count toward the same bound.
                for old_key, old in list(self._entries.items()):
                    if old.done and old.expires_at <= now:
                        del self._entries[old_key]
                entry = self._entries.get(key)
                if entry is not None:
                    self._entries.move_to_end(key)
                    break
                if len(self._entries) >= self.max_entries:
                    victim = next((k for k, item in self._entries.items() if item.done), None)
                    if victim is None:
                        self._condition.wait(timeout=min(WAIT_SECONDS, left))
                        continue
                    del self._entries[victim]
                entry = _Entry(end=now + left)
                self._entries[key] = entry
                owner = True
                break
            entry.callers[caller] = deadline

        try:
            if owner:
                self._fill(key, entry, pinned, reader)
            with self._condition:
                while not entry.done:
                    self._condition.wait(timeout=min(WAIT_SECONDS, deadline.remaining()))
                deadline.remaining()
                if entry.failure is not None:
                    raise Problem(*entry.failure)
                summaries = entry.summaries
            # Every projection creates new models. No caller can mutate the
            # cached tuple or receive notes for another dataset.
            result = project_diagnostics(summaries, dataset)
            deadline.remaining()
            return result
        finally:
            with self._condition:
                entry.callers.pop(caller, None)
                self._condition.notify_all()

    def _fill(self, key, entry, pinned, reader):
        """Verify outside the lock, then publish one success or wake failed waiters."""
        shared = _FillDeadline(entry, self._condition, self.clock)
        try:
            shared.remaining()
            summaries = read_verified_diagnostics(pinned, reader, shared)
            shared.remaining()
        except BaseException as error:
            # Retain only safe status/code for existing waiters, not exception
            # tracebacks containing raw evidence. Even an interrupted owner
            # must wake them and remove the pending entry.
            failure = (error.status, error.code) if isinstance(error, Problem) else (503, 'dependency_unavailable')
            with self._condition:
                entry.failure, entry.done = failure, True
                del self._entries[key]
                self._condition.notify_all()
            raise
        with self._condition:
            entry.summaries = summaries
            entry.expires_at = self.clock() + self.ttl_seconds
            entry.done = True
            self._condition.notify_all()
