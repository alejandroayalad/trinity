"""Closed analytical operations without database or storage authority."""

from dataclasses import asdict, dataclass, field
import hashlib
import json


@dataclass(frozen=True)
class OutputColumn:
    """Preserve each public label and direct-source unit by position."""
    name: str
    unit: str | None


@dataclass(frozen=True)
class ValidatedQuery:
    """Bind the original input to a deterministic, versioned policy result."""
    original_sql: str = field(repr=False)
    dataset: str
    operation: str = field(repr=False)
    columns: tuple[OutputColumn, ...]
    policy_version: int = 1

    def to_bytes(self) -> bytes:
        """Encode the bounded internal message, never a public response."""
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()

    @property
    def digest(self) -> str:
        """Bind every policy field without authorizing a file location."""
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, data: bytes) -> "ValidatedQuery":
        """Reject noncanonical, oversized or extended internal messages."""
        try:
            if len(data) > 256 * 1024:
                raise ValueError
            body = json.loads(data)
            if set(body) != {"original_sql", "dataset", "operation", "columns", "policy_version"}:
                raise ValueError
            if (type(body["policy_version"]) is not int or body["policy_version"] != 1
                    or any(type(body[k]) is not str for k in ("original_sql", "dataset", "operation"))
                    or type(body["columns"]) is not list or not 1 <= len(body["columns"]) <= 128):
                raise ValueError
            columns = []
            for c in body["columns"]:
                if (set(c) != {"name", "unit"} or type(c["name"]) is not str
                        or not 1 <= len(c["name"]) <= 128 or c["unit"] not in (None, "MW", "percent")):
                    raise ValueError
                columns.append(OutputColumn(**c))
            body["columns"] = tuple(columns)
            result = cls(**body)
            if result.to_bytes() != data:
                raise ValueError
            return result
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError("Invalid policy message.") from None


@dataclass(frozen=True)
class PreviewOperation:
    """Bind typed filters and a full continuation key to one publication."""
    dataset: str
    publication_event_id: str
    version_id: str
    start: str
    end: str
    facility: str | None = None
    generator: str | None = None
    page_size: int = 100
    after: tuple[str, ...] | None = None
    protocol_version: int = 1
    kind: str = 'preview'

    def __post_init__(self):
        from datetime import date
        import re
        from uuid import UUID
        from trinity.contracts.datasets import DATASETS

        def day(value):
            if type(value) is not str or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None:
                raise ValueError('Invalid preview operation')
            return date.fromisoformat(value)

        def identifier(value):
            if type(value) is not str or not 1 <= len(value) <= 128 or not value.strip():
                raise ValueError('Invalid preview operation')
            value.encode('utf-8')

        if (type(self.protocol_version) is not int or self.protocol_version != 1
                or self.kind != 'preview' or self.dataset not in DATASETS
                or type(self.page_size) is not int or not 1 <= self.page_size <= 1000):
            raise ValueError('Invalid preview operation')
        for value in (self.publication_event_id, self.version_id):
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError('Invalid preview operation')
        start, end = day(self.start), day(self.end)
        if not 0 <= (end - start).days < 366:
            raise ValueError('Invalid preview operation')
        for value in (self.facility, self.generator):
            if value is not None:
                identifier(value)
        if (self.dataset == 'national' and (self.facility is not None or self.generator is not None)
                or self.generator is not None and (self.dataset != 'generator' or self.facility is None)):
            raise ValueError('Invalid preview operation')
        if self.after is not None:
            if type(self.after) is not tuple or len(self.after) != len(DATASETS[self.dataset].key_fields):
                raise ValueError('Invalid preview operation')
            if not start <= day(self.after[0]) <= end:
                raise ValueError('Invalid preview operation')
            for value in self.after[1:]:
                identifier(value)
            if (self.facility is not None and self.after[1] != self.facility
                    or self.generator is not None and self.after[2] != self.generator):
                raise ValueError('Invalid preview operation')

    def to_bytes(self) -> bytes:
        """Use canonical bytes so every filter participates in result binding."""
        return canonical_message(asdict(self))

    @property
    def digest(self) -> str:
        """Bind filters, page position and publication to the runtime result."""
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PreviewOperation':
        """Reject SQL, paths, extra fields and invalid full-key positions."""
        try:
            if len(data) > 8192:
                raise ValueError
            body = json.loads(data)
            if set(body) != set(cls.__dataclass_fields__):
                raise ValueError
            if body['after'] is not None:
                if type(body['after']) is not list:
                    raise ValueError
                body['after'] = tuple(body['after'])
            result = cls(**body)
            if result.to_bytes() != data:
                raise ValueError
            return result
        except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, RecursionError):
            raise ValueError('Invalid preview operation') from None


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 320 * 1024
BINDING_FIELDS = ('protocol_version', 'request_id', 'version_id', 'operation_kind', 'operation_digest')


def canonical_message(body) -> bytes:
    """Encode one deterministic representation for digest and version checks."""
    return json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def request_message(request_id, version_id, operation) -> dict:
    """Tag the operation explicitly; old or cross-kind envelopes cannot execute."""
    from uuid import UUID
    from trinity.contracts.choices import ChoiceOperation
    request_id, version_id = str(request_id), str(version_id)
    if any(str(UUID(value)) != value for value in (request_id, version_id)):
        raise ValueError('Invalid request binding')
    if type(operation) not in (ValidatedQuery, PreviewOperation, ChoiceOperation):
        raise ValueError('Invalid operation')
    if isinstance(operation, (PreviewOperation, ChoiceOperation)) and operation.version_id != version_id:
        raise ValueError('Invalid request binding')
    return dict(protocol_version=PROTOCOL_VERSION, request_id=request_id, version_id=version_id,
                operation_kind=operation.kind if isinstance(operation, (PreviewOperation, ChoiceOperation)) else 'sql',
                operation=json.loads(operation.to_bytes()), operation_digest=operation.digest)


def read_request(data: bytes):
    """Validate the closed envelope before any table registration."""
    from trinity.contracts.choices import ChoiceOperation
    try:
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError
        body = json.loads(data)
        if (set(body) != {*BINDING_FIELDS, 'operation'}
                or type(body['protocol_version']) is not int or body['protocol_version'] != PROTOCOL_VERSION):
            raise ValueError
        kind = body['operation_kind']
        if kind not in ('sql', 'preview', 'choices'):
            raise ValueError
        decoder = {'preview': PreviewOperation, 'choices': ChoiceOperation, 'sql': ValidatedQuery}[kind]
        operation = decoder.from_bytes(canonical_message(body['operation']))
        expected = request_message(body['request_id'], body['version_id'], operation)
        if expected != body or canonical_message(expected) != data:
            raise ValueError
        return body, operation
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, RecursionError):
        raise ValueError('Invalid query request') from None


def read_result_binding(body, request_id, version_id, operation):
    """Accept a result only for the exact operation launched by this owner."""
    expected = request_message(request_id, version_id, operation)
    if (type(body) is not dict or set(body) != {*BINDING_FIELDS, 'result'}
            or type(body['protocol_version']) is not int
            or any(body[key] != expected[key] for key in BINDING_FIELDS)
            or type(body['result']) is not dict):
        raise ValueError('Invalid query result')
    return body['result']
