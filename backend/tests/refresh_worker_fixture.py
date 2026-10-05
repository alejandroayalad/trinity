"""Share synthetic object bytes between real preparation and recovery processes."""
from collections.abc import MutableMapping
from pathlib import Path

from test_prepare import fixture_worker
from test_s3 import MemoryS3
from trinity.adapters.s3 import S3Storage


class DiskObjects(MutableMapping):
    """Retain only the synthetic SDK objects in a test-owned remote directory."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(exist_ok=True)

    def __getitem__(self, key):
        try:
            return (self.root/key).read_bytes()
        except FileNotFoundError:
            raise KeyError(key) from None

    def __setitem__(self, key, value):
        path = self.root/key
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(value)

    def __delitem__(self, key):
        (self.root/key).unlink()

    def __iter__(self):
        return (str(path.relative_to(self.root)) for path in self.root.rglob('*') if path.is_file())

    def __len__(self):
        return sum(1 for _ in self)


def storage(root, settings):
    """Read the bytes the real child wrote, rather than reconstructing evidence."""
    client = MemoryS3()
    client.objects = DiskObjects(Path(root)/'remote')
    return S3Storage(settings,client=client)


def shared_child(request, connection):
    """Inject shared synthetic storage while keeping the production pipeline."""
    import test_prepare
    def client():
        result = MemoryS3()
        result.objects = DiskObjects(request['root'].parent/'remote')
        return result
    test_prepare.MemoryS3 = client
    fixture_worker(request,connection)
