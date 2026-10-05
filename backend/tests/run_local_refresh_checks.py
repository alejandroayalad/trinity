"""Run BullMQ/Redis and PostgreSQL acceptance using only disposable services."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    """Start isolated Redis, delegate SQL lifecycle, and remove only our container."""
    docker=os.environ.get('TRINITY_DOCKER_BIN','/Applications/Docker.app/Contents/Resources/bin/docker')
    container=subprocess.check_output([docker,'run','--rm','-d','-p','127.0.0.1::6379',
        'redis:8.10.2','redis-server','--save','','--appendonly','no','--maxmemory-policy','noeviction'],text=True).strip()
    try:
        port=subprocess.check_output([docker,'port',container,'6379/tcp'],text=True).strip().rsplit(':',1)[1]
        env={**os.environ,'TRINITY_TEST_REDIS_PORT':port}
        return subprocess.call([sys.executable,str(Path(__file__).with_name('run_local_sql_checks.py')),
                               '--refresh',*sys.argv[1:]],env=env)
    finally:
        subprocess.run([docker,'stop','-t','2',container],check=True,stdout=subprocess.DEVNULL)


if __name__=='__main__':
    raise SystemExit(main())
