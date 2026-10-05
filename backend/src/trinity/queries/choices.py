"""Authenticate choice bookmarks and validate closed distinct-ID result pages."""
from dataclasses import dataclass, replace
import hashlib
import hmac
from types import SimpleNamespace
from uuid import UUID

from pydantic import Field
from trinity.auth.schemas import StrictModel, Publication
from trinity.contracts.queries import ChoiceOperation
from trinity.errors import Problem
from trinity.queries.cursors import _decode, _encode
from trinity.queries.preview import PreviewInput, ResolvedPreview, parse_preview_input, resolve_preview, source_id
from trinity.queries.preview_schemas import PreviewRange
from trinity.queries.service import PreviewService


@dataclass(frozen=True, repr=False)
class ChoiceInput(PreviewInput):
    """Keep literal search separate from source identifiers and preview filters."""
    search: str | None = None


@dataclass(frozen=True, repr=False)
class ResolvedChoice(ResolvedPreview):
    """Bind a literal search to the resolved date and parent tuple."""
    search: str | None = None


class ChoicePage(StrictModel):
    """Keep the response bounded and the parent explicit for generator choices."""
    publication: Publication
    range: PreviewRange
    items: list[dict[str, str | None]] = Field(max_length=100)
    next_cursor: str | None
    facility: str | None = None


class ChoiceCodec:
    """Use existing key configuration with a distinct purpose and authenticated body."""
    def __init__(self, keys, selection):
        self.keys, self.selection = keys, selection

    def encode(self, operation, after):
        """Sign the entire closed next operation; never sign file authority."""
        next_operation = replace(operation, after_id=after)
        payload = next_operation.to_bytes()
        prefix = 'ch1.' + self.keys.active_id + '.' + _encode(payload)
        signature = hmac.digest(self.keys.keys[self.keys.active_id].get_secret_value(), prefix.encode(), hashlib.sha256)
        return prefix + '.' + _encode(signature)

    def decode(self, token):
        """Authenticate before decoding and reject cross-purpose bookmarks."""
        try:
            if type(token) is not str or len(token) > 4096:
                raise ValueError
            version, key, payload, signature = token.split('.')
            if version != 'ch1' or key not in self.keys.keys:
                raise ValueError
            prefix = '.'.join((version, key, payload))
            expected = hmac.digest(self.keys.keys[key].get_secret_value(), prefix.encode(), hashlib.sha256)
            if not hmac.compare_digest(_decode(signature), expected):
                raise ValueError
            operation = ChoiceOperation.from_bytes(_decode(payload))
            if operation.selection != self.selection or operation.after_id is None:
                raise ValueError
            return operation
        except (ValueError, TypeError, KeyError, AttributeError):
            raise Problem(422, 'invalid_cursor') from None


def build_choice_response(operation, publication, batch, codec):
    """Validate order, exact IDs, parent, count and lookahead before signing."""
    try:
        if (type(batch) is not dict or set(batch) != {'items', 'has_more'}
                or type(batch['items']) is not list or type(batch['has_more']) is not bool
                or len(batch['items']) > operation.page_size
                or batch['has_more'] and len(batch['items']) != operation.page_size):
            raise ValueError
        previous = operation.after_id
        field = 'facility' if operation.selection == 'facilities' else 'generator'
        for item in batch['items']:
            expected = {'facility', 'facilityName'} if operation.selection == 'facilities' else {'facility', 'generator'}
            if type(item) is not dict or set(item) != expected:
                raise ValueError
            identifier = source_id(item[field])
            if previous is not None and identifier.encode() <= previous.encode():
                raise ValueError
            if field == 'generator' and item['facility'] != operation.facility:
                raise ValueError
            if field == 'facility' and item['facilityName'] is not None and (type(item['facilityName']) is not str or not item['facilityName'].strip()):
                raise ValueError
            previous = identifier
        return ChoicePage(publication=publication, range=PreviewRange(start=operation.start, end=operation.end),
                          items=batch['items'], next_cursor=codec.encode(operation, previous) if batch['has_more'] else None,
                          facility=operation.facility if field == 'generator' else None)
    except (ValueError, TypeError, KeyError):
        raise Problem(503, 'dependency_unavailable') from None


class ChoiceService(PreviewService):
    """Reuse shared authority, rate, capacity, provenance and isolated execution."""
    def __init__(self, *args, selection, **kwargs):
        from trinity.queries.cursors import load_cursor_keys
        super().__init__(*args, **kwargs)
        self.selection = selection
        self.codec_factory = lambda: ChoiceCodec(load_cursor_keys(), selection)

    def authorize(self, principal, dataset_key):
        """Hide unsupported and unauthorized choice datasets before any debit."""
        from trinity.auth.permissions import require
        if dataset_key not in ('facility_outages', 'generator_outages') or self.selection == 'generators' and dataset_key != 'generator_outages':
            raise Problem(404, 'dataset_not_found')
        dataset = super().authorize(principal, dataset_key)
        require(principal, 'preview:detail')
        return dataset

    def parse_input(self, pairs, *, body):
        """Parse choice-only fields before the normal shared debit boundary."""
        search = None
        remaining = []
        for name, value in pairs:
            if name == 'search':
                if self.selection != 'facilities' or search is not None or type(value) is not str or not 1 <= len(value) <= 100:
                    raise Problem(422, 'invalid_request')
                search = value
            elif name not in ('start', 'end', 'facility', 'limit', 'cursor'):
                raise Problem(422, 'invalid_request')
            else:
                remaining.append((name, value))
        request = parse_preview_input(remaining, body=body)
        limit = request.limit if any(k == 'limit' for k, _ in remaining) else 50
        if limit > 100:
            raise Problem(422, 'invalid_request')
        return ChoiceInput(request.start, request.end, request.facility, None, limit, request.cursor, search)

    def validate_input(self, dataset, request):
        """Deny national choices and enforce the generator parent after debit."""
        super().validate_input(dataset, request)
        if (dataset == 'national' or self.selection == 'generators' and (dataset != 'generator' or request.facility is None)
                or self.selection == 'facilities' and request.facility is not None):
            raise Problem(422, 'invalid_request')

    def decode_position(self, codec, request):
        """Expose only enough authenticated position data for the shared flow."""
        if request.cursor is None:
            return None
        operation = codec.decode(request.cursor)
        from trinity.queries.preview import strict_date
        resolved = ResolvedChoice(operation.dataset, strict_date(operation.start), strict_date(operation.end),
                                  operation.facility, None, operation.page_size, operation.search)
        return SimpleNamespace(request=resolved, operation=operation)

    def resolve_input(self, dataset, request, latest):
        """Resolve date defaults once and retain literal search text."""
        resolved = resolve_preview(dataset, request, latest)
        return ResolvedChoice(resolved.dataset, resolved.start, resolved.end, resolved.facility,
                              None, resolved.limit, request.search)

    def resolve_position(self, position, dataset, request, publication):
        """Publication changes require a restart; changed search or parent is invalid."""
        if publication is None or publication.publication_event_id != UUID(position.operation.publication_event_id):
            raise Problem(409, 'publication_changed')
        resolved = self.resolve_input(dataset, request, publication.latest_observation_date)
        if resolved != position.request:
            raise Problem(422, 'invalid_cursor')
        return resolved

    def operation(self, dataset, pinned, resolved, position):
        """Send no SQL, signing key or file path into the closed runtime message."""
        return ChoiceOperation(dataset, str(pinned.publication.publication_event_id), str(pinned.publication.version_id),
                               resolved.start.isoformat(), resolved.end.isoformat(), facility=resolved.facility,
                               page_size=resolved.limit, selection=self.selection, search=resolved.search,
                               after_id=position.operation.after_id if position else None)
