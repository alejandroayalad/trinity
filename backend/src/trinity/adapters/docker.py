"""Bounded local Docker operations for one fixed query image and volume."""

import json
import re
import socket
import struct
from urllib.parse import urlencode

import httpx
from trinity.errors import Problem

MAX_OUTPUT = 6 * 1024 * 1024


class _Stream:
    def __init__(self, connection, initial, deadline):
        self.connection, self.buffer, self.deadline = connection, bytearray(initial), deadline

    def read(self, length, *, eof=False):
        while len(self.buffer) < length:
            self.connection.settimeout(min(2, self.deadline.remaining()))
            try: block = self.connection.recv(min(65536, length-len(self.buffer)))
            except socket.timeout:
                self.deadline.remaining(); continue
            if not block:
                if eof and not self.buffer: return b''
                raise Problem(503, 'dependency_unavailable')
            self.buffer.extend(block)
        result=bytes(self.buffer[:length]);del self.buffer[:length]
        return result


def read_frames(stream):
    """Read complete non-TTY frames; bound both channels before allocation."""
    output, errors = bytearray(), 0
    while True:
        header=stream.read(8,eof=True)
        if not header: return bytes(output)
        channel, length=header[0],struct.unpack('>I',header[4:])[0]
        if header[1:4] != b'\0\0\0' or channel not in (1,2):
            raise Problem(503,'dependency_unavailable')
        if (channel==1 and len(output)+length>MAX_OUTPUT or channel==2 and errors+length>8192):
            raise Problem(503,'query_resource_limit')
        data=stream.read(length)
        if channel==1:output.extend(data)
        else:errors+=length


class Docker:
    """Use only a configured Unix socket; never pull images or accept remote URLs."""
    def __init__(self, socket_path, image, volume):
        if (not socket_path.startswith('/') or not re.fullmatch(r'sha256:[0-9a-f]{64}',image)
                or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}',volume)):
            raise Problem(503,'dependency_unavailable')
        self.socket_path,self.image,self.volume=socket_path,image,volume
        self.client=httpx.Client(transport=httpx.HTTPTransport(uds=socket_path),base_url='http://docker',timeout=2)
        self.version=''
        server=self.call('GET','/version')
        api=tuple(int(p) for p in server['ApiVersion'].split('.'))
        minimum=tuple(int(p) for p in server.get('MinAPIVersion','1.24').split('.'))
        if api<(1,47) or minimum>(1,56):raise Problem(503,'dependency_unavailable')
        self.version='/v'+'.'.join(map(str,min(api,(1,56))))
        self.daemon_id=self.call('GET','/info')['ID']
        if self.call('GET',f'/images/{image}/json')['Id']!=image:
            raise Problem(503,'dependency_unavailable')

    def call(self,method,path,*,body=None,allow_missing=False):
        try:
            with self.client.stream(method,self.version+path,json=body) as response:
                if allow_missing and response.status_code==404:return None
                if response.status_code not in (200,201,204,304):raise Problem(503,'dependency_unavailable')
                data=bytearray()
                for chunk in response.iter_bytes():
                    if len(data)+len(chunk)>1024*1024:raise Problem(503,'dependency_unavailable')
                    data.extend(chunk)
                return json.loads(data) if data else {}
        except Problem:raise
        except Exception:raise Problem(503,'dependency_unavailable') from None

    def create(self,reservation):
        request=str(reservation['request_id'])
        labels={'trinity.query':request,'trinity.deployment':str(reservation['deployment_id'])}
        config={
            'Image':self.image,'User':'10001:10001','WorkingDir':'/query','Entrypoint':['/opt/venv/bin/python'],
            'Cmd':['-m','trinity.queries.runtime'],'Env':['PATH=/opt/venv/bin:/usr/bin:/bin',
                'PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1'],
            'Tty':False,'OpenStdin':False,'AttachStdout':True,'AttachStderr':True,'Labels':labels,
            'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'CapDrop':['ALL'],
                'SecurityOpt':['no-new-privileges'],'Memory':1073741824,'MemorySwap':1073741824,
                'NanoCpus':1000000000,'PidsLimit':64,'AutoRemove':False,'RestartPolicy':{'Name':'no'},
                'LogConfig':{'Type':'none','Config':{}},
                'Tmpfs':{'/tmp':'rw,noexec,nosuid,nodev,size=33554432'},
                'Mounts':[{'Type':'volume','Source':self.volume,'Target':'/query','ReadOnly':True,
                           'VolumeOptions':{'NoCopy':True,'Subpath':request}}]},
        }
        return self.call('POST','/containers/create?'+urlencode({'name':reservation['container_name']}),body=config)['Id']

    def inspect(self,identifier):
        return self.call('GET',f'/containers/{identifier}/json',allow_missing=True)

    def verify(self,info,reservation):
        """Refuse launch if the daemon did not retain every required restriction."""
        host,config=info['HostConfig'],info['Config']
        expected={'trinity.query':str(reservation['request_id']),'trinity.deployment':str(reservation['deployment_id'])}
        mounts=host.get('Mounts',[])
        if (info['Image']!=self.image or config['User']!='10001:10001' or config['Tty']
                or config['Entrypoint']!=['/opt/venv/bin/python'] or config['Cmd']!=['-m','trinity.queries.runtime']
                or any(config.get('Labels',{}).get(k)!=v for k,v in expected.items())
                or host['NetworkMode']!='none' or not host['ReadonlyRootfs'] or host.get('Privileged')
                or host.get('CapAdd') or host.get('Devices') or host['CapDrop']!=['ALL']
                or not any(x.startswith('no-new-privileges') for x in host['SecurityOpt'])
                or any('unconfined' in x for x in host['SecurityOpt'])
                or host['Memory']!=1073741824 or host['MemorySwap']!=1073741824
                or host['NanoCpus']!=1000000000 or host['PidsLimit']!=64 or host['AutoRemove']
                or host['LogConfig']['Type']!='none' or host['RestartPolicy']['Name']!='no'
                or len(mounts)!=1 or mounts[0].get('Source')!=self.volume
                or mounts[0].get('Target')!='/query' or not mounts[0].get('ReadOnly')
                or mounts[0].get('VolumeOptions',{}).get('Subpath')!=str(reservation['request_id'])):
            raise Problem(503,'dependency_unavailable')
        env_names={value.split('=',1)[0] for value in config['Env']}
        if not env_names <= {'PATH','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','LANG','GPG_KEY','PYTHON_VERSION','PYTHON_SHA256'}:
            raise Problem(503,'dependency_unavailable')

    def attach(self,identifier,deadline):
        """Open attach before start; require Docker's upgraded raw frame stream."""
        connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            connection.settimeout(min(2,deadline.remaining()));connection.connect(self.socket_path)
            path=f'{self.version}/containers/{identifier}/attach?stream=1&stdout=1&stderr=1'
            connection.sendall((f'POST {path} HTTP/1.1\r\nHost: docker\r\nConnection: Upgrade\r\n'
                                'Upgrade: tcp\r\nContent-Length: 0\r\n\r\n').encode())
            data=bytearray()
            while b'\r\n\r\n' not in data:
                block=connection.recv(1024)
                if not block or len(data)+len(block)>8192:raise Problem(503,'dependency_unavailable')
                data.extend(block)
            header,initial=bytes(data).split(b'\r\n\r\n',1)
            if not header.startswith(b'HTTP/1.1 101 '):raise Problem(503,'dependency_unavailable')
            return connection,_Stream(connection,initial,deadline)
        except Exception:
            connection.close();raise Problem(503,'dependency_unavailable') from None

    def start(self,identifier):self.call('POST',f'/containers/{identifier}/start')

    def remove_stopped(self,identifier,reservation):
        """Confirm identity, kill if needed, and remove the immutable ID."""
        info=self.inspect(identifier)
        if info is None:return
        labels=info.get('Config',{}).get('Labels',{})
        if (info['Id']!=identifier or labels.get('trinity.query')!=str(reservation['request_id'])
                or labels.get('trinity.deployment')!=str(reservation['deployment_id'])):
            raise Problem(503,'dependency_unavailable')
        if info['State']['Running']:
            self.call('POST',f'/containers/{identifier}/kill?signal=SIGKILL')
        info=self.inspect(identifier)
        if info is not None and info['State']['Running']:raise Problem(503,'dependency_unavailable')
        self.call('DELETE',f'/containers/{identifier}',allow_missing=True)
        if self.inspect(identifier) is not None:raise Problem(503,'dependency_unavailable')
