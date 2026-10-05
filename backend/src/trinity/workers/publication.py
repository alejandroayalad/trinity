"""Run one synchronous publisher under the retained original process lock."""
import asyncio
from pathlib import Path
from uuid import UUID

from trinity.adapters.queue import publication_payload
from trinity.publication.custody import custody
from trinity.publication.service import PublicationService


class PublicationWorker:
    """Keep process custody in the synchronous thread even if async wait cancels."""
    def __init__(self, database, root, storage_factory):
        self.service = PublicationService(database)
        self.root = Path(root)
        self.storage_factory = storage_factory

    def execute(self, payload):
        """Resolve trusted custody, then claim and verify at most once."""
        payload = publication_payload(payload)
        run = self.service.lookup(UUID(payload['run_id']))
        if not run:
            return None
        # The service resolves existing events before obsolete ownership checks.
        with self.service.transaction(readonly=True) as c:
            event = c.execute('SELECT * FROM publication_events WHERE version_id=%s',
                              (UUID(payload['version_id']),)).fetchone()
            if event:
                version = c.execute('SELECT run_id FROM data_versions WHERE id=%s',(event['version_id'],)).fetchone()
                return event if version['run_id'] == run['id'] else None
        with custody(self.root,run):
            return self.service.execute(payload,self.root,storage_factory=self.storage_factory)

    async def process(self, job, _token):
        """Let BullMQ renew transport while the thread retains its own lock."""
        await asyncio.to_thread(self.execute,job.data)
