"""Verify Unified Expedition builds and saved-spec gates through the HTTP API."""
from . import streamed_smoke


def smoke(workspace):
    return streamed_smoke.smoke(workspace, 'unified')


if __name__ == '__main__':
    streamed_smoke.main('unified', __doc__)
