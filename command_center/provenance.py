"""Canonical spec identities for exact snapshot-to-project release checks."""
import hashlib
import json


def spec_digest(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
