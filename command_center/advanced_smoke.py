"""Build and verify the Advanced City fixture and a custom city through the HTTP API."""
from . import streamed_smoke


def smoke(workspace):
    return streamed_smoke.smoke(workspace, 'advanced')


if __name__ == '__main__':
    streamed_smoke.main('advanced', __doc__)
