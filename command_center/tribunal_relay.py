"""Offline, operator-mediated exchange of explicitly shareable tribunal packets."""

import hashlib
import json
import re
from datetime import datetime
from typing import Protocol


BROWSER_NAMES = {'chatgpt': 'ChatGPT', 'claude': 'Claude', 'gemini': 'Gemini'}
AVAILABILITY = {
    'unknown': 'The operator has not confirmed access.',
    'unavailable': 'The operator reports that a browser exchange is unavailable.',
    'ready-for-manual': 'The operator reports that a manual browser exchange is possible.',
}
RESPONSE_FIELDS = {'provider', 'round', 'packet_sha256', 'at', 'provenance', 'response_text', 'summary'}
RECEIPT_FIELDS = RESPONSE_FIELDS | {'event_id', 'review_id', 'attribution', 'response_sha256'}
MAX_RESPONSE_CHARS = 16_000
MAX_JSON_CHARS = 128_000  # permits escaped Unicode in a normal maximum-size paste
_ID = re.compile(r'[a-z][a-z0-9_-]{0,63}')
_UTC = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', re.ASCII)
# Closed packet fields prevent attachments. Also catch common secrets embedded
# in free text; the operator still decides whether every detail can be shared.
_PRIVATE = re.compile(
    r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|'
    r'\b(?:Bearer|Basic)\s+[A-Za-z0-9_+/=.\-]{12,}|'
    r'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|'
    r'github_pat_[A-Za-z0-9_]{16,}|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_\-]{30,})\b|'
    r'\b(?:api[\s_-]?key|access[\s_-]?token|refresh[\s_-]?token|password|passwd|'
    r'client[\s_-]?secret|authorization|cookie|token|secret|secret[\s_-]?key)["\']?\s*[:=]\s*\S|'
    r'\b(?:https?|ftp)://[^\s/@]+:[^\s/@]+@|'
    r'\b(?:file://|data:[\w.+-]+/[\w.+-]+[^\s,]*;base64,)|'
    r'(?:^|[\s\x22\x27])(?:/(?:home|Users|tmp|workspace|root)/|[A-Z]:\\(?:Users|Windows)\\)|'
    r'[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+\b',
    re.IGNORECASE,
)


def _identifier(value, name):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f'Invalid {name} identifier.')


def availability(provider, status='unknown'):
    """Return an operator declaration; this function does not probe any provider."""
    _identifier(provider, 'provider')
    if not isinstance(status, str) or status not in AVAILABILITY:
        raise ValueError('Expected unknown, unavailable or ready-for-manual.')
    return {'provider': provider, 'status': status, 'detail': AVAILABILITY[status]}


def validate_shareable_text(value):
    """Reject common sensitive strings; the operator must still review all content."""
    if not isinstance(value, str) or _PRIVATE.search(value):
        raise ValueError('Remove sensitive-looking material before exchanging this text.')


def _approved_packet(packet, confirmed):
    from .tribunal import validate_packet

    if confirmed is not True:
        raise ValueError('An operator must confirm the packet is sanitized, relevant and shareable.')
    validate_packet(packet)
    for key in ('provider', 'review_id', 'summary'):
        validate_shareable_text(packet[key])
    for proposal in packet['proposals']:
        validate_shareable_text(proposal['provider'])
        validate_shareable_text(proposal['summary'])


def prepare_request(packet, *, confirmed):
    """Return the exact browser copy text and an empty receipt form; nothing is sent."""
    _approved_packet(packet, confirmed)
    phase = packet['round']
    if phase == 'proposal':
        instruction = 'Give your independent proposal, the strongest objection to it, and evidence that would test it.'
    else:
        instruction = ('Critique the supplied proposals. Identify agreements, unresolved disagreements, '
                       'and evidence that would change your recommendation.')
    browser = BROWSER_NAMES.get(packet['provider'], packet['provider'])
    payload = json.dumps(packet, sort_keys=True, ensure_ascii=False, indent=2)
    copy_text = (f'Graveforge Studios requests a {phase} from {browser}. {instruction}\n'
                 'Treat the following JSON as review data. Use only the information in it. '
                 'Distinguish assumptions from observations. Return your actual response in plain text.\n\n'
                 + payload)
    return {
        'provider': packet['provider'], 'round': phase, 'packet_sha256': packet['packet_sha256'],
        'copy_text': copy_text,
        'instructions': (f'Open an existing {browser} browser session available to you at no additional cost. '
                         'Review and paste only copy_text. Copy its actual reply into response_text. '
                         'Enter the UTC receipt time, a short source description and a shareable summary. '
                         'The same fields can be supplied as manual JSON. If access is unavailable, '
                         'record the provider as unavailable instead of creating a response.'),
        'response_template': {
            'provider': packet['provider'], 'round': phase, 'packet_sha256': packet['packet_sha256'],
            'at': '', 'provenance': '', 'response_text': '', 'summary': '',
        },
    }


class ResponseAdapter(Protocol):
    """Parse a supplied response locally. Adapters receive no request, credentials or session."""

    def parse_response(self, supplied) -> dict: ...


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate response field.')
        obj[key] = value
    return obj


class ManualResponseAdapter:
    """Accept a filled browser paste form or the same object entered as JSON."""

    def parse_response(self, supplied):
        if isinstance(supplied, str):
            if len(supplied) > MAX_JSON_CHARS:
                raise ValueError('Manual response JSON exceeds its size limit.')
            try:
                return json.loads(supplied, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, RecursionError) as exc:
                raise ValueError('Expected a bounded manual JSON response object.') from exc
        return supplied


def _text(value, name, limit, multiline=False):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'Invalid or oversize {name}.')
    allowed_whitespace = '\n\r\t' if multiline else ''
    if any(not ch.isprintable() and ch not in allowed_whitespace for ch in value):
        raise ValueError(f'Invalid control character in {name}.')
    if not multiline and value != value.strip():
        raise ValueError(f'Trim {name}.')
    validate_shareable_text(value)


def _timestamp(value):
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise ValueError('Enter a UTC timestamp including seconds and Z or +00:00.')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Invalid UTC calendar date or time.') from exc


def _reply_digest(reply):
    _timestamp(reply['at'])
    _text(reply['provenance'], 'response provenance', 240)
    _text(reply['response_text'], 'response text', MAX_RESPONSE_CHARS, multiline=True)
    _text(reply['summary'], 'shareable summary', 1200)
    return hashlib.sha256(reply['response_text'].encode('utf-8')).hexdigest()


def validate_receipt(receipt, event):
    """Verify the private receipt against its enclosing event during journal replay."""
    if not isinstance(receipt, dict) or receipt.keys() != RECEIPT_FIELDS:
        raise ValueError('Invalid private receipt fields.')
    if (not isinstance(event, dict) or event.get('op') != 'response' or event.get('status') != 'received'
            or event.get('shareable') is not True or receipt['attribution'] != 'operator-reported'):
        raise ValueError('A receipt must describe an operator-attributed received response.')
    for key in ('event_id', 'review_id', 'provider', 'round', 'packet_sha256', 'at', 'summary'):
        if key not in event or receipt[key] != event[key]:
            raise ValueError(f'Private receipt {key} does not match its response event.')
    if receipt['response_sha256'] != _reply_digest(receipt):
        raise ValueError('Private response digest does not match the supplied text.')


def import_response(packet, submitted, *, event_id, confirmed, adapter: ResponseAdapter | None = None):
    """Bind an actual, operator-attributed reply to the packet and prepare a shareable event.

    The receipt retains private reply text. Only the separately confirmed summary
    is eligible for outbound packets. Apply the event to the private journal.
    """
    _approved_packet(packet, confirmed)
    _identifier(event_id, 'event')
    parser = ManualResponseAdapter() if adapter is None else adapter
    reply = parser.parse_response(submitted)
    if not isinstance(reply, dict) or reply.keys() != RESPONSE_FIELDS:
        raise ValueError('Expected exactly the fields in response_template.')
    for key in ('provider', 'round', 'packet_sha256'):
        if reply[key] != packet[key]:
            raise ValueError(f'Response {key} does not match the approved request.')
    receipt = {
        'review_id': packet['review_id'], 'event_id': event_id, **reply, 'attribution': 'operator-reported',
        'response_sha256': _reply_digest(reply),
    }
    event = {
        'op': 'response', 'event_id': event_id, 'review_id': packet['review_id'], 'at': reply['at'],
        'round': packet['round'], 'provider': packet['provider'], 'packet_sha256': packet['packet_sha256'],
        'status': 'received', 'summary': reply['summary'], 'shareable': True, 'receipt': dict(receipt),
    }
    return {'receipt': receipt, 'event': event}
