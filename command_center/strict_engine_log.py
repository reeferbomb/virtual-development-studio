"""Classify Godot console records separately from the contents of QA proof markers."""

import hashlib
import re


_CSI = re.compile(rb'\x1b\[[0-?]*[ -/]*[@-~]')
_ENGINE_ERROR = re.compile(rb'(?:(?:user|shader|parse|compile) +)?error\s*:|fatal error\s*:', re.I)
_FAIL_RECORD = re.compile(
    rb'(?:\[(?:fail|failed|failure)\]|(?:fail(?:ed|ure)?|(?:test|check|assertion) fail(?:ed|ure)?)\b)', re.I)
_COUNT = re.compile(
    rb'(?:^|[ ,\t])(?:failures|failed (?:checks|tests)|(?:checks|tests) failed)\s*[:=]\s*(\d+)\s*$', re.I)


def _diagnostic(line):
    line = _CSI.sub(b'', line).strip()
    upper = line.upper()
    if upper.startswith(b'SCRIPT ERROR:'):
        return 'SCRIPT ERROR'
    if _ENGINE_ERROR.match(line):
        return 'ERROR'
    if upper.startswith((b'WARNING:', b'USER WARNING:', b'SCRIPT WARNING:', b'SHADER WARNING:')):
        return 'WARNING'
    # Studio's scripted tests print both "FAIL <check>" and named summaries
    # such as "lobby checks=6 failures=1". A summary of zero is a clean line.
    count = _COUNT.search(line)
    if count and count[1].strip(b'0'):
        return 'FAIL'
    if count and count.start() == 0:
        return None
    if _FAIL_RECORD.match(line):
        return 'FAIL'
    return None


def has_engine_error(output):
    """A fixed engine probe permits warnings; its caller validates the proof marker."""
    return any(_diagnostic(line) in ('SCRIPT ERROR', 'ERROR', 'FAIL') for line in output.splitlines())


def inspect_log(stream):
    """Hash the exact combined output and count each diagnostic record once."""
    digest = hashlib.sha256()
    counts = {}
    for chunk in stream:
        digest.update(chunk)
        for line in chunk.splitlines():
            category = _diagnostic(line)
            if category is not None:
                counts[category] = counts.get(category, 0) + 1
    return digest.hexdigest(), counts
