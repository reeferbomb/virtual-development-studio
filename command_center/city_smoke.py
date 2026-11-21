"""Build and verify the Metropolis fixture and a custom city through the HTTP API."""
from . import streamed_smoke


def smoke(workspace):
    return streamed_smoke.smoke(workspace, 'city')


if __name__ == '__main__':
    streamed_smoke.main('city', __doc__)
