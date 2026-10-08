"""App identity shared by local build, signing and device tools."""
import re

DEFAULT_BUNDLE_ID = 'com.konradkern.pt.native'


def bundle_id(value):
    if not isinstance(value, str) or len(value) > 200 or not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', value):
        raise ValueError('bundle ID must contain at least two nonempty ASCII components')
    return value


def test_bundle_ids(value):
    value = bundle_id(value)
    # Keep the installed development harness identifiers compatible by default.
    harness = 'com.konradkern.pt.harness' if value == DEFAULT_BUNDLE_ID else value + '.harness'
    return harness, harness + '.tests.xctrunner'
