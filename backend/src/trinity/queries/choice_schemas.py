"""Validate choice output before signing pagination or exposing runtime values."""

from pydantic import Field, field_validator

from trinity.auth.schemas import Publication, StrictModel
from trinity.contracts.choices import matches_search
from trinity.errors import Problem
from trinity.queries.preview import source_id
from trinity.queries.preview_schemas import PreviewRange


class FacilityOption(StrictModel):
    """Preserve a Plant's source ID and its latest non-null display name."""
    facility: str = Field(min_length=1, max_length=128)
    facilityName: str | None = Field(max_length=256)

    @field_validator('facility')
    @classmethod
    def exact_identifier(cls, value):
        return source_id(value)


class GeneratorOption(StrictModel):
    """Keep the parent because generator IDs are not globally unique."""
    facility: str = Field(min_length=1, max_length=128)
    generator: str = Field(min_length=1, max_length=128)

    @field_validator('facility', 'generator')
    @classmethod
    def exact_identifier(cls, value):
        return source_id(value)


class FacilityOptions(StrictModel):
    """Return only the existing OpenAPI choice envelope."""
    publication: Publication
    range: PreviewRange
    items: list[FacilityOption] = Field(max_length=100)
    next_cursor: str | None = Field(max_length=4096)


class GeneratorOptions(StrictModel):
    """Include the exact selected Plant even for an empty generator page."""
    publication: Publication
    range: PreviewRange
    facility: str = Field(min_length=1, max_length=128)
    items: list[GeneratorOption] = Field(max_length=100)
    next_cursor: str | None = Field(max_length=4096)


def build_choice_response(operation, publication, batch, *, codec):
    """Check binding, ordering, parent and search before returning a signed page.

    The runtime has already reduced the full range. This check must never
    deduplicate or silently discard invalid output, since doing so can hide a
    truncated page. Invalid results fail before the supervisor reports success.
    """
    try:
        if (type(batch) is not dict or set(batch) != {'items', 'has_more'}
                or type(batch['items']) is not list or type(batch['has_more']) is not bool
                or len(batch['items']) > operation.page_size
                or batch['has_more'] and len(batch['items']) != operation.page_size
                or operation.version_id != str(publication.version_id)
                or operation.publication_event_id != str(publication.publication_event_id)):
            raise ValueError
        model = FacilityOption if operation.choice == 'facilities' else GeneratorOption
        items = [model.model_validate(item) for item in batch['items']]
        previous = operation.after.encode('utf-8') if operation.after is not None else None
        for item in items:
            identifier = item.facility if operation.choice == 'facilities' else item.generator
            key = identifier.encode('utf-8')
            if previous is not None and key <= previous:
                raise ValueError
            if operation.choice == 'generators' and item.facility != operation.facility:
                raise ValueError
            if not matches_search(identifier, getattr(item, 'facilityName', None), operation.search):
                raise ValueError
            previous = key
        if operation.after is not None and not items:
            raise ValueError
        cursor = codec.encode(operation, identifier) if batch['has_more'] else None
        body = dict(publication=publication, range=PreviewRange(start=operation.start, end=operation.end),
                    items=items, next_cursor=cursor)
        if operation.choice == 'generators':
            return GeneratorOptions(**body, facility=operation.facility)
        return FacilityOptions(**body)
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError):
        raise Problem(503, 'dependency_unavailable') from None
