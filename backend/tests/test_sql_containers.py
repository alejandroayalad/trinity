"""Opt-in real Docker tests; own and remove only uniquely named test resources."""
import io
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest
from uuid import uuid4

from trinity.adapters.docker import Docker, read_frames, _Stream
from trinity.queries.service import QueryDeadline
from trinity.queries.runtime.sql_policy import validate_query
from trinity.queries.staging import stage_query, PublishedReader
from trinity.errors import Problem
from test_sql_staging import bundle, Client
from types import SimpleNamespace

IMAGE=os.environ.get('TRINITY_TEST_QUERY_IMAGE')
DOCKER='/Applications/Docker.app/Contents/Resources/bin/docker' if Path('/Applications/Docker.app').exists() else 'docker'
SOCKET=os.environ.get('TRINITY_TEST_DOCKER_SOCKET','/var/run/docker.sock')


class FrameTests(unittest.TestCase):
    def test_partial_frames_and_safe_stderr(self):
        left,right=socket.socketpair();self.addCleanup(left.close);self.addCleanup(right.close)
        raw=b'\x02\0\0\0'+struct.pack('>I',3)+b'err'+b'\x01\0\0\0'+struct.pack('>I',2)+b'{}'
        right.sendall(raw);right.shutdown(socket.SHUT_WR)
        self.assertEqual(read_frames(_Stream(left,b'',QueryDeadline(2))),b'{}')

    def test_huge_frame_and_partial_eof_fail(self):
        for raw in (b'\x01\0\0\0'+struct.pack('>I',7*1024*1024),b'\x01\0'):
            left,right=socket.socketpair()
            try:
                right.sendall(raw);right.shutdown(socket.SHUT_WR)
                with self.assertRaises(Problem):read_frames(_Stream(left,b'',QueryDeadline(2)))
            finally:left.close();right.close()


@unittest.skipUnless(IMAGE,'Explicit disposable Docker test image required')
class ContainerTests(unittest.TestCase):
    def cli(self,*args):
        return subprocess.check_output([DOCKER,*args],stderr=subprocess.DEVNULL,text=True).strip()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.stage=self.root/'stage';self.stage.mkdir()
        (self.stage/'sibling-secret').write_text('synthetic sibling')
        self.pinned,objects=bundle(self.root/'source')
        self.query=validate_query('SELECT COUNT(*), SUM(outage) FROM national_outages')
        self.request=uuid4();self.deployment=uuid4()
        self.staged=stage_query(self.stage,self.request,self.pinned,self.query,
            PublishedReader(Client(objects),SimpleNamespace(bucket='test',prefix='versions')),QueryDeadline(30))
        self.volume='trinity-sql-test-'+uuid4().hex
        self.cli('volume','create',self.volume)
        self.addCleanup(lambda:self.cli('volume','rm',self.volume))
        helper=self.cli('create','--entrypoint','/bin/true','--user','0','--mount',f'type=volume,src={self.volume},dst=/staging',IMAGE)
        try:self.cli('cp',str(self.stage)+'/.',helper+':/staging')
        finally:self.cli('rm',helper)
        self.docker=Docker(SOCKET,IMAGE,self.volume);self.addCleanup(self.docker.client.close)
        self.reservation={'request_id':self.request,'deployment_id':self.deployment,
                          'container_name':'trinity-query-'+str(self.request)}
        self.identifier=None
        def cleanup():
            if self.identifier:self.docker.remove_stopped(self.identifier,self.reservation)
        self.addCleanup(cleanup)

    def test_real_runtime_has_restricted_mount_and_returns_exact_result(self):
        self.identifier=self.docker.create(self.reservation)
        info=self.docker.inspect(self.identifier);self.docker.verify(info,self.reservation)
        self.assertEqual(info['HostConfig']['NetworkMode'],'none')
        self.assertEqual(len(info['Mounts']),1)
        self.assertFalse(info['Mounts'][0]['RW'])
        from copy import deepcopy
        altered = deepcopy(info)
        altered['Config']['Cmd'] = ['-c', 'print(1)']
        with self.assertRaises(Problem):
            self.docker.verify(altered, self.reservation)
        connection,stream=self.docker.attach(self.identifier,QueryDeadline(30))
        try:
            self.docker.start(self.identifier);body=json.loads(read_frames(stream))
        finally:connection.close()
        self.assertEqual(body['request_id'],str(self.request))
        self.assertEqual(body['operation_digest'],self.query.digest)
        self.assertEqual(body['result']['rows'],[['6','12.000000']])

    def test_probe_cannot_use_network_write_mount_or_read_siblings(self):
        original=self.docker.call
        script="""import json,os,socket
results=[]
for action in (lambda: open('/query/request.json','wb'), lambda: open('/query/sibling-secret','rb'),
               lambda: socket.create_connection(('1.1.1.1',53),timeout=.2)):
 try: action();results.append(False)
 except OSError: results.append(True)
results.append(not any(k.startswith(('AWS_','TRINITY_','PGPASSWORD')) for k in os.environ))
print(json.dumps(results))
"""
        def call(method,path,**kw):
            if path.startswith('/containers/create?'):kw['body']['Cmd']=['-c',script]
            return original(method,path,**kw)
        self.docker.call=call
        self.identifier=self.docker.create(self.reservation)
        connection,stream=self.docker.attach(self.identifier,QueryDeadline(30))
        try:self.docker.start(self.identifier);result=json.loads(read_frames(stream))
        finally:connection.close()
        self.assertEqual(result,[True,True,True,True])

    def test_timeout_stops_and_removes_known_container(self):
        original=self.docker.call
        def call(method,path,**kw):
            if path.startswith('/containers/create?'):kw['body']['Cmd']=['-c','import time; time.sleep(60)']
            return original(method,path,**kw)
        self.docker.call=call
        self.identifier=self.docker.create(self.reservation)
        connection,stream=self.docker.attach(self.identifier,QueryDeadline(1))
        try:
            self.docker.start(self.identifier)
            with self.assertRaises(Problem):read_frames(stream)
        finally:connection.close()
        self.docker.remove_stopped(self.identifier,self.reservation)
        self.assertIsNone(self.docker.inspect(self.identifier))

    def test_wrong_ownership_cannot_remove_a_container(self):
        self.identifier=self.docker.create(self.reservation)
        with self.assertRaises(Problem):self.docker.remove_stopped(self.identifier,{**self.reservation,'deployment_id':uuid4()})
        self.assertIsNotNone(self.docker.inspect(self.identifier))

    def test_memory_ceiling_is_enforced_by_the_kernel(self):
        original=self.docker.call
        def call(method,path,**kw):
            if path.startswith('/containers/create?'):kw['body']['Cmd']=['-c','x=bytearray(2*1024*1024*1024)']
            return original(method,path,**kw)
        self.docker.call=call
        self.identifier=self.docker.create(self.reservation)
        connection,stream=self.docker.attach(self.identifier,QueryDeadline(30))
        try:self.docker.start(self.identifier);read_frames(stream)
        finally:connection.close()
        limit=time.monotonic()+5
        while self.docker.inspect(self.identifier)['State']['Running'] and time.monotonic()<limit:time.sleep(.05)
        info=self.docker.inspect(self.identifier)
        self.assertFalse(info['State']['Running'])
        self.assertTrue(info['State']['OOMKilled'])
