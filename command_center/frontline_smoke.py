"""Build and verify the Frontline City fixture and a custom city through the HTTP API."""

from . import streamed_smoke


def smoke(workspace):
    return streamed_smoke.smoke(workspace, 'frontline')


if __name__ == '__main__':
    streamed_smoke.main('frontline', __doc__)
