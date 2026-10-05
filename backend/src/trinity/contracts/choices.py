"""Carry closed filter-choice operations into the credential-free runtime."""

from dataclasses import asdict, dataclass
import hashlib
import json

from trinity.contracts.queries import PreviewOperation, canonical_message


@dataclass(frozen=True)
class ChoiceOperation:
    """Bind one distinct-entity page to its dataset, range and publication.

    Only facilities and generators are supported. Search is literal Unicode
    case-folded text, applied to an ID or its displayed label. The continuation
    is an exact source ID, not a daily preview key or a storage location.
    """
    dataset: str
    publication_event_id: str
    version_id: str
    start: str
    end: str
    choice: str = 'facilities'
    facility: str | None = None
    search: str | None = None
    page_size: int = 50
    after: str | None = None
    protocol_version: int = 1
    kind: str = 'choices'

    def __post_init__(self):
        # Reuse lexical/range validation without broadening the preview protocol.
        PreviewOperation(self.dataset, self.publication_event_id, self.version_id,
                         self.start, self.end, self.facility, page_size=self.page_size)
        if (self.kind != 'choices' or type(self.protocol_version) is not int
                or self.protocol_version != 1 or self.choice not in ('facilities', 'generators')
                or self.dataset not in ('facility', 'generator') or self.page_size > 100):
            raise ValueError('Invalid choice operation')
        if (self.choice == 'facilities' and self.facility is not None
                or self.choice == 'generators' and (self.dataset != 'generator'
                    or self.facility is None or self.search is not None)):
            raise ValueError('Invalid choice operation')
        for value, maximum in ((self.search, 100), (self.after, 128)):
            if value is not None:
                if type(value) is not str or not 1 <= len(value) <= maximum or not value.strip():
                    raise ValueError('Invalid choice operation')
                value.encode('utf-8')

    def to_bytes(self) -> bytes:
        """Bind every input in canonical bytes without caller-supplied SQL."""
        return canonical_message(asdict(self))

    @property
    def digest(self) -> str:
        """Identify the exact operation expected by the supervisor."""
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ChoiceOperation':
        """Reject extra fields, alternate encodings and malformed typed values."""
        try:
            if type(data) is not bytes or len(data) > 8192:
                raise ValueError
            body = json.loads(data)
            if type(body) is not dict or set(body) != set(cls.__dataclass_fields__):
                raise ValueError
            operation = cls(**body)
            if operation.to_bytes() != data:
                raise ValueError
            return operation
        except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, RecursionError):
            raise ValueError('Invalid choice operation') from None


def matches_search(identifier: str, label: str | None, search: str | None) -> bool:
    """Treat %, _, quotes and Unicode as literal text, without normalization."""
    return search is None or any(search.casefold() in value.casefold()
                                 for value in (identifier, label or ''))


