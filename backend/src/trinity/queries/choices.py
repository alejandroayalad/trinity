"""Validate Plant choice requests and authenticate purpose-specific bookmarks."""

from dataclasses import asdict, dataclass, replace
import hashlib
import hmac

from trinity.contracts.choices import ChoiceOperation
from trinity.contracts.queries import canonical_message
from trinity.errors import Problem
from trinity.queries.cursors import (
    CursorKeys, KEY_ID, MAX_CURSOR, MAX_PAYLOAD, _canonical, _decode, _encode, _json,
)
from trinity.queries.preview import PreviewInput, authorize_preview, parse_preview_input, resolve_preview


def authorize_choices(principal, dataset_key, choice):
    """Deny hidden datasets before inspecting request input or storage."""
    dataset = authorize_preview(principal, dataset_key)
    if dataset == 'national' or choice == 'generators' and dataset != 'generator':
        raise Problem(404, 'dataset_not_found')
    return dataset


@dataclass(frozen=True, repr=False)
class ChoiceInput:
    """Keep primitive parsing separate from rate-counted semantic checks."""
    preview: PreviewInput
    search: str | None


def parse_choice_input(pairs, choice, *, body=b'') -> ChoiceInput:
    """Preserve duplicates and exact identifiers; search is facilities-only."""
    try:
        if isinstance(pairs, (str, bytes, dict)):
            raise ValueError
        values = []
        search = None
        names = set()
        allowed = {'start', 'end', 'limit', 'cursor',
                   'search' if choice == 'facilities' else 'facility'}
        for name, value in pairs:
            if name not in allowed or name in names:
                raise ValueError
            names.add(name)
            if name == 'search':
                if type(value) is not str or not 1 <= len(value) <= 100 or not value.strip():
                    raise ValueError
                value.encode('utf-8')
                search = value
            else:
                values.append((name, value))
        if 'limit' not in names:
            values.append(('limit', '50'))
        preview = parse_preview_input(values, body=body)
        if preview.limit > 100:
            raise ValueError
        return ChoiceInput(preview, search)
    except (ValueError, TypeError, UnicodeError):
        raise Problem(422, 'invalid_request') from None


def resolve_choices(dataset, choice, request, publication) -> ChoiceOperation:
    """Use preview date defaults while retaining exact search and parent IDs."""
    resolved = resolve_preview(dataset, request.preview, publication.latest_observation_date)
    try:
        return ChoiceOperation(dataset, str(publication.publication_event_id), str(publication.version_id),
                               resolved.start.isoformat(), resolved.end.isoformat(), choice,
                               resolved.facility, request.search, resolved.limit)
    except ValueError:
        raise Problem(422, 'invalid_request') from None


class ChoiceCursorCodec:
    """Reuse the key ring with a distinct prefix and operation-bound payload.

    Bookmarks carry neither permission nor file authority. The service checks
    the current session and publication on every page. No time-only expiry is
    added; a changed publication, key, route or effective filter rejects reuse.
    """
    def __init__(self, keys: CursorKeys):
        self.keys = keys

    def encode(self, operation: ChoiceOperation, after: str) -> str:
        """Sign only a validated operation and its last returned exact ID."""
        try:
            positioned = replace(operation, after=after)
            # UTF-8 keeps maximum-length Unicode IDs inside the public token limit.
            payload = _canonical(asdict(positioned))
            if len(payload) > MAX_PAYLOAD:
                raise ValueError
            prefix = 'ch1.' + self.keys.active_id + '.' + _encode(payload)
            secret = self.keys.keys[self.keys.active_id].get_secret_value()
            token = prefix + '.' + _encode(hmac.digest(secret, prefix.encode('ascii'), hashlib.sha256))
            if len(token) > MAX_CURSOR:
                raise ValueError
            return token
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise Problem(503, 'dependency_unavailable') from None

    def decode(self, token: str) -> ChoiceOperation:
        """Authenticate before decoding; preview and other-purpose tokens fail."""
        try:
            if type(token) is not str or not 1 <= len(token) <= MAX_CURSOR:
                raise ValueError
            parts = token.split('.')
            if len(parts) != 4:
                raise ValueError
            version, key_id, payload_text, signature = parts
            if version != 'ch1' or KEY_ID.fullmatch(key_id) is None or key_id not in self.keys.keys:
                raise ValueError
            if len(payload_text) > 4000 or len(signature) != 43:
                raise ValueError
            prefix = '.'.join(parts[:3]).encode('ascii')
            secret = self.keys.keys[key_id].get_secret_value()
            if not hmac.compare_digest(_decode(signature), hmac.digest(secret, prefix, hashlib.sha256)):
                raise ValueError
            payload = _decode(payload_text)
            if len(payload) > MAX_PAYLOAD:
                raise ValueError
            body = _json(payload.decode('utf-8'))
            if _canonical(body) != payload:
                raise ValueError
            operation = ChoiceOperation.from_bytes(canonical_message(body))
            if operation.after is None:
                raise ValueError
            return operation
        except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, RecursionError):
            raise Problem(422, 'invalid_cursor') from None
