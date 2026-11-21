"""Verify Living World builds and saved-spec gates through the HTTP API."""
from . import streamed_smoke


def smoke(workspace):
    return streamed_smoke.smoke(workspace, 'living')


if __name__ == '__main__':
    streamed_smoke.main('living', __doc__)
