"""Authenticate bounded preview bookmarks; never grant identity or file access."""

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
import re
from types import MappingProxyType
from uuid import UUID

from pydantic import SecretBytes

from trinity.auth.schemas import Publication
from trinity.errors import Problem
from trinity.queries.preview import (
    DATASETS, PUBLIC_DATASETS, PreviewInput, ResolvedPreview, resolve_preview,
    strict_date, validate_key,
)

MAX_CURSOR = 4096
MAX_PAYLOAD = 3000
KEY_ID = re.compile(r'[A-Za-z0-9_-]{1,32}')
FIELDS = frozenset(('version', 'purpose', 'dataset', 'publication_event_id', 'start', 'end',
                    'facility', 'generator', 'limit', 'after'))


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _decode(value: str) -> bytes:
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_-]+', value) is None:
        raise ValueError
    decoded = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    if _encode(decoded) != value:
        raise ValueError
    return decoded


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(_value):
    raise ValueError


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)


def _canonical(body):
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


@dataclass(frozen=True)
class CursorKeys:
    """Keep a bounded immutable key ring with redacted representations."""
    active_id: str
    keys: dict[str, SecretBytes] = field(repr=False)

    def __post_init__(self):
        try:
            if type(self.active_id) is not str or KEY_ID.fullmatch(self.active_id) is None:
                raise ValueError
            if not 1 <= len(self.keys) <= 4 or self.active_id not in self.keys:
                raise ValueError
            for key_id, secret in self.keys.items():
                if (type(key_id) is not str or KEY_ID.fullmatch(key_id) is None
                        or not isinstance(secret, SecretBytes) or len(secret.get_secret_value()) != 32):
                    raise ValueError
            object.__setattr__(self, 'keys', MappingProxyType(dict(self.keys)))
        except (ValueError, TypeError, AttributeError):
            raise Problem(503, 'dependency_unavailable') from None


def load_cursor_keys(environ=None) -> CursorKeys:
    """Load explicitly at use time; no startup key generation or .env loading."""
    try:
        source = os.environ if environ is None else environ
        raw = source['TRINITY_PREVIEW_CURSOR_KEYS_JSON']
        if type(raw) is not str or len(raw) > 4096 or len(raw.encode('utf-8')) > 4096:
            raise ValueError
        body = _json(raw)
        if type(body) is not dict or not 1 <= len(body) <= 4:
            raise ValueError
        keys = {}
        for key_id, encoded in body.items():
            if type(encoded) is not str or len(encoded) != 43:
                raise ValueError
            keys[key_id] = SecretBytes(_decode(encoded))
        return CursorKeys(source['TRINITY_PREVIEW_CURSOR_ACTIVE_KEY_ID'], keys)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Problem(503, 'dependency_unavailable') from None


@dataclass(frozen=True, repr=False)
class CursorPosition:
    """Hold authenticated position data, not user or publication authority."""
    request: ResolvedPreview
    publication_event_id: UUID
    after: tuple[str, ...]


class CursorCodec:
    """Sign bookmarks and authenticate complete input before parsing its payload."""
    def __init__(self, keys: CursorKeys):
        self.keys = keys

    def encode(self, request: ResolvedPreview, publication_event_id: UUID, after) -> str:
        """Sign a validated last-returned key; malformed trusted state fails closed."""
        try:
            if type(publication_event_id) is not UUID:
                raise ValueError
            key = validate_key(request, after)
            body = {'version': 1, 'purpose': 'dataset-preview',
                    'dataset': DATASETS[request.dataset].table_name,
                    'publication_event_id': str(publication_event_id),
                    'start': request.start.isoformat(), 'end': request.end.isoformat(),
                    'facility': request.facility, 'generator': request.generator,
                    'limit': request.limit, 'after': list(key)}
            payload = _canonical(body)
            if len(payload) > MAX_PAYLOAD:
                raise ValueError
            prefix = 'pv1.' + self.keys.active_id + '.' + _encode(payload)
            secret = self.keys.keys[self.keys.active_id].get_secret_value()
            token = prefix + '.' + _encode(hmac.digest(secret, prefix.encode('ascii'), hashlib.sha256))
            if len(token) > MAX_CURSOR:
                raise ValueError
            return token
        except (ValueError, TypeError, KeyError, UnicodeError, AttributeError):
            raise Problem(503, 'dependency_unavailable') from None

    def decode(self, token: str) -> CursorPosition:
        """Reject extended, noncanonical or unauthenticated tokens with one safe code."""
        try:
            if type(token) is not str or not 1 <= len(token) <= MAX_CURSOR:
                raise ValueError
            parts = token.split('.')
            if len(parts) != 4:
                raise ValueError
            version, key_id, payload_text, signature = parts
            if version != 'pv1' or KEY_ID.fullmatch(key_id) is None or key_id not in self.keys.keys:
                raise ValueError
            if len(payload_text) > 4000 or len(signature) != 43:
                raise ValueError
            prefix = '.'.join(parts[:3]).encode('ascii')
            secret = self.keys.keys[key_id].get_secret_value()
            tag = _decode(signature)
            if len(tag) != 32 or not hmac.compare_digest(tag, hmac.digest(secret, prefix, hashlib.sha256)):
                raise ValueError
            payload = _decode(payload_text)
            if len(payload) > MAX_PAYLOAD:
                raise ValueError
            body = _json(payload.decode('utf-8'))
            if type(body) is not dict or set(body) != FIELDS or _canonical(body) != payload:
                raise ValueError
            if type(body['version']) is not int or body['version'] != 1 or body['purpose'] != 'dataset-preview':
                raise ValueError
            if type(body['dataset']) is not str or body['dataset'] not in PUBLIC_DATASETS:
                raise ValueError
            publication = UUID(body['publication_event_id'])
            if str(publication) != body['publication_event_id']:
                raise ValueError
            request = ResolvedPreview(PUBLIC_DATASETS[body['dataset']], strict_date(body['start']),
                                      strict_date(body['end']), body['facility'], body['generator'], body['limit'])
            after = validate_key(request, body['after'])
            return CursorPosition(request, publication, after)
        except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, RecursionError, Problem):
            raise Problem(422, 'invalid_cursor') from None


def resolve_continuation(position: CursorPosition, dataset: str, request: PreviewInput,
                         publication: Publication | None) -> ResolvedPreview:
    """Compare current publication before defaults; the caller must reauthorize."""
    if position.request.dataset != dataset:
        raise Problem(422, 'invalid_cursor')
    if publication is None or publication.publication_event_id != position.publication_event_id:
        raise Problem(409, 'publication_changed')
    resolved = resolve_preview(dataset, request, publication.latest_observation_date)
    if resolved != position.request:
        raise Problem(422, 'invalid_cursor')
    return resolved
