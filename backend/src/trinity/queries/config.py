"""Load lazy trusted query configuration, independent of auth and health."""
from pathlib import Path
import os
from uuid import UUID

import boto3
from botocore.config import Config

from trinity.adapters.docker import Docker
from trinity.config import S3Settings
from trinity.errors import Problem
from trinity.queries.client import QueryExecution
from trinity.queries.staging import PublishedReader


def execution_factory(database, *, recovery=False):
    """Require an explicit read profile, immutable image and named staging volume."""
    try:
        root=Path(os.environ['TRINITY_QUERY_STAGE_ROOT'])
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():raise ValueError
        deployment=UUID(os.environ['TRINITY_QUERY_DEPLOYMENT_ID'])
        reader=None
        if not recovery:
            settings=S3Settings(bucket=os.environ['TRINITY_S3_BUCKET'],prefix=os.environ['TRINITY_S3_PREFIX'],
                            region=os.environ['TRINITY_S3_REGION'])
            profile=os.environ['TRINITY_QUERY_READ_PROFILE']
            if not profile:raise ValueError
            session=boto3.Session(profile_name=profile)
            client=session.client('s3',region_name=settings.region,config=Config(connect_timeout=2,read_timeout=2,
                retries={'total_max_attempts':1},ignore_configured_endpoint_urls=True))
            reader=PublishedReader(client,settings)
        docker=Docker(os.environ['TRINITY_DOCKER_SOCKET'],os.environ['TRINITY_QUERY_IMAGE'],
                      os.environ['TRINITY_QUERY_STAGE_VOLUME'])
        return QueryExecution(database,docker,reader,root,deployment)
    except Problem:raise
    except Exception:raise Problem(503,'dependency_unavailable') from None
