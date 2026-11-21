"""Build and verify the Vertical City fixture and a custom city through the HTTP API."""
from . import streamed_smoke


def smoke(workspace):
    return streamed_smoke.smoke(workspace, 'vertical')


if __name__ == '__main__':
    streamed_smoke.main('vertical', __doc__)
