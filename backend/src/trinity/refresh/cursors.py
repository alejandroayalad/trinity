"""Sign refresh history positions with purpose and sequence bounds.

Reuse the existing cursor key-ring validation and canonical encoding helpers.
Separate key configuration and the rf1 prefix prevent a Preview bookmark from
being accepted as a refresh position. Bookmarks never grant Admin authority.
"""
import hashlib
import hmac
import os

from trinity.errors import Problem
from trinity.queries.cursors import (
    CursorKeys, KEY_ID, _canonical, _decode, _encode, _json, load_cursor_keys,
)


def load_refresh_keys():
    """Use explicitly configured keys; never generate a restart-local secret."""
    try:
        return load_cursor_keys({
            'TRINITY_PREVIEW_CURSOR_KEYS_JSON':os.environ['TRINITY_REFRESH_CURSOR_KEYS_JSON'],
            'TRINITY_PREVIEW_CURSOR_ACTIVE_KEY_ID':os.environ['TRINITY_REFRESH_CURSOR_ACTIVE_KEY_ID'],
        })
    except KeyError:
        raise Problem(503,'dependency_unavailable') from None


class RefreshCursorCodec:
    """Authenticate a small fixed schema before a service uses any sequence."""
    def __init__(self, keys: CursorKeys):
        self.keys = keys

    def encode(self, *, purpose, target, limit, maximum, after):
        """Bind the last row and original maximum; later rows cannot shift pages."""
        body = dict(purpose=purpose,target=target,limit=limit,maximum=maximum,after=after)
        self._validate(body,purpose,target,limit)
        prefix = 'rf1.'+self.keys.active_id+'.'+_encode(_canonical(body))
        secret = self.keys.keys[self.keys.active_id].get_secret_value()
        return prefix+'.'+_encode(hmac.digest(secret,prefix.encode('ascii'),hashlib.sha256))

    def decode(self, token, *, purpose, target, limit):
        """Reject cross-run, cross-purpose, changed-size and forged cursors."""
        try:
            if type(token) is not str or not 1<=len(token)<=4096:
                raise ValueError
            version,key,payload,signature = token.split('.')
            if version!='rf1' or KEY_ID.fullmatch(key) is None or key not in self.keys.keys:
                raise ValueError
            prefix = '.'.join((version,key,payload))
            secret = self.keys.keys[key].get_secret_value()
            if not hmac.compare_digest(_decode(signature),hmac.digest(secret,prefix.encode('ascii'),hashlib.sha256)):
                raise ValueError
            raw = _decode(payload)
            body = _json(raw)
            if _canonical(body)!=raw:
                raise ValueError
            self._validate(body,purpose,target,limit)
            return body
        except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, RecursionError):
            raise Problem(422,'invalid_cursor') from None

    @staticmethod
    def _validate(body,purpose,target,limit):
        """Restrict both counters to PostgreSQL bigint and the selected page size."""
        if (type(body) is not dict or set(body)!={'purpose','target','limit','maximum','after'}
                or purpose not in ('refresh-history','refresh-steps')
                or body['purpose']!=purpose or body['target']!=target
                or type(body['limit']) is not int or not 1<=body['limit']<=100
                or (limit is not None and body['limit']!=limit)
                or any(type(body[k]) is not int for k in ('maximum','after'))
                or not 0<body['after']<=body['maximum']<=9223372036854775807):
            raise ValueError
