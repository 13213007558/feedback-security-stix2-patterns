"""
Tests for strict STIX version selection.

An explicitly supplied version must always be honoured, and an unknown version
must raise instead of silently falling back to the default (2.1) or to 2.0.
"""
import pytest

from stix2patterns import DEFAULT_VERSION, SUPPORTED_VERSIONS
from stix2patterns.exceptions import UnknownSTIXVersionError
from stix2patterns.validator import resolve_stix_version, run_validator, validate


def test_default_is_latest():
    assert DEFAULT_VERSION == '2.1'
    assert SUPPORTED_VERSIONS == ('2.0', '2.1')


def test_none_resolves_to_default():
    assert resolve_stix_version(None) == DEFAULT_VERSION


def test_explicit_versions_are_honoured():
    assert resolve_stix_version('2.0') == '2.0'
    assert resolve_stix_version('2.1') == '2.1'


@pytest.mark.parametrize('bad_version',
                         ['2.2', '3.0', '', '2.1 ', 'v2.1', 2.1, 2, None][:-1])
def test_unknown_version_raises(bad_version):
    with pytest.raises(UnknownSTIXVersionError) as exc:
        resolve_stix_version(bad_version)
    assert str(bad_version) in str(exc.value)
    for supported in SUPPORTED_VERSIONS:
        assert supported in str(exc.value)


def test_explicit_version_not_overridden_by_default():
    # EXISTS is 2.1-only. An explicit 2.0 request must reject it even though
    # the library default is 2.1.
    exists_pattern = '[EXISTS file:name]'
    assert run_validator(exists_pattern, stix_version='2.1') == []
    assert run_validator(exists_pattern, stix_version='2.0') != []

    # And a normal pattern validates identically regardless of explicit choice.
    common = '[file:size = 1280]'
    assert run_validator(common, stix_version='2.0') == []
    assert run_validator(common, stix_version='2.1') == []


def test_run_validator_unknown_version_raises():
    with pytest.raises(UnknownSTIXVersionError):
        run_validator('[file:size = 1]', stix_version='9.9')


def test_validate_unknown_version_raises():
    with pytest.raises(UnknownSTIXVersionError):
        validate('[file:size = 1]', stix_version='9.9')


def test_unknown_error_does_not_mention_fallback():
    with pytest.raises(UnknownSTIXVersionError) as exc:
        resolve_stix_version('1.0')
    message = str(exc.value).lower()
    assert 'fallback' not in message
    assert 'default' not in message
