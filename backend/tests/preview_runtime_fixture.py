"""Bridge native test staging to a disposable Docker volume without cloud access."""
import io
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import uuid4

from trinity.adapters.docker import Docker
from trinity.queries.client import QueryExecution
from trinity.queries.staging import PublishedReader
from test_sql_containers import DOCKER

IMAGE = os.environ.get('TRINITY_TEST_QUERY_IMAGE')
SOCKET = os.environ.get('TRINITY_TEST_DOCKER_SOCKET', '/var/run/docker.sock')


def cli(*args):
    return subprocess.check_output([DOCKER,*args],stderr=subprocess.DEVNULL,text=True).strip()


class ObjectClient:
    """Serve exact producer bytes; count each attempted GET and allow fault hooks."""
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.before_get = None

    def add(self, version, objects):
        self.objects.update({f'versions/{version}/{path}':data for path,data in objects.items()})

    def get_object(self, *, Bucket, Key):
        self.calls.append(Key)
        if self.before_get is not None:
            self.before_get(Key)
        data = self.objects[Key]
        return {'Body':io.BytesIO(data),'ContentLength':len(data)}


class BridgeDocker(Docker):
    """Copy only this request before launch; production still uses a shared volume."""
    def __init__(self, sandbox):
        self.sandbox = sandbox
        super().__init__(SOCKET, IMAGE, sandbox.volume)

    def create(self, reservation):
        request = str(reservation['request_id'])
        helper = cli('create','--entrypoint','/bin/true','--user','0','--network','none',
                     '--mount',f'type=volume,src={self.volume},dst=/staging',IMAGE)
        try:
            cli('cp',str(self.sandbox.stage/request),helper+':/staging/'+request)
        finally:
            cli('rm',helper)
        # Suspend before the real daemon request to test late creation after
        # recovery has claimed ownership and inspected an absent container.
        if self.sandbox.before_create:
            self.sandbox.before_create(reservation)
        identifier = super().create(reservation)
        self.sandbox.created.append(identifier)
        if self.sandbox.after_create:
            self.sandbox.after_create(identifier)
        return identifier

    def call(self, method, path, **kwargs):
        if path.startswith('/containers/create?') and self.sandbox.command is not None:
            kwargs['body']['Cmd'] = ['-c',self.sandbox.command]
        return super().call(method,path,**kwargs)

    def verify(self, info, reservation):
        if self.sandbox.command is None:
            return super().verify(info, reservation)
        # Fault probes have an explicit test workload. Check that exact command
        # and the real isolation settings; ordinary previews use Docker.verify.
        from trinity.errors import Problem
        if info['Config']['Cmd'] != ['-c', self.sandbox.command]:
            raise Problem(503, 'dependency_unavailable')
        self._verify_isolation(info, reservation)

    def start(self, identifier):
        if self.sandbox.before_start:
            self.sandbox.before_start(identifier)
        super().start(identifier)
        if self.sandbox.after_start:
            self.sandbox.after_start(identifier)

    def remove_stopped(self, identifier, reservation):
        if self.sandbox.before_remove:
            self.sandbox.before_remove(identifier)
        return super().remove_stopped(identifier,reservation)


class RuntimeSandbox:
    """Own only uniquely named test resources and keep their cleanup independently checkable."""
    def __init__(self, database, stage, *, volume=None, deployment=None):
        self.database, self.stage = database, Path(stage)
        self.stage.mkdir(parents=True,exist_ok=True)
        self.volume = volume or 'trinity-preview-test-'+uuid4().hex
        self.deployment = deployment or uuid4()
        self.created = []
        self.command = self.before_create = self.after_create = None
        self.before_start = self.after_start = self.before_remove = None
        self.client = ObjectClient()
        self.sleep = None
        if volume is None:
            cli('volume','create',self.volume)

    def execution(self):
        reader = PublishedReader(self.client,SimpleNamespace(bucket='synthetic',prefix='versions'))
        if self.sleep is not None:
            reader.sleep = self.sleep
        return QueryExecution(self.database,BridgeDocker(self),reader,self.stage,self.deployment)

    def remaining_containers(self):
        return cli('ps','-aq','--filter',f'label=trinity.deployment={self.deployment}').split()

    def close(self):
        # Failure cleanup is restricted to this fixture's random deployment label.
        for identifier in self.remaining_containers():
            cli('rm','-f',identifier)
        cli('volume','rm',self.volume)
