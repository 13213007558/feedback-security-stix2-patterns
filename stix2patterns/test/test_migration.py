"""
Tests for the STIX 2.0 -> 2.1 migration compatibility checker.

Coverage is built around the genuine, documented differences between the two
grammars plus control samples that behave identically on both sides:

* EXISTS / NOT EXISTS  -> 2.1-only syntax (v21_only)
* duplicate qualifiers -> legal in 2.0, rejected in 2.1 (needs_manual_review)
* ordinary patterns    -> valid under both (compatible)
* malformed patterns   -> invalid under both (invalid)

The checker must retain both real parse results and the original text and must
never rewrite an expression.
"""
import io
import json

import pytest

from stix2patterns import migration
from stix2patterns.migration import (
    COMPATIBLE, INVALID, NEEDS_MANUAL_REVIEW, V21_ONLY,
    check_pattern, check_patterns, main, read_patterns, render_json_report,
    render_text_report, result_to_dict, summarize,
)
from stix2patterns.validator import run_validator

# --- Real cross-version differences ---------------------------------------

V21_ONLY_PATTERNS = [
    '[EXISTS file:name]',
    '[NOT EXISTS file:hashes.\'SHA-256\']',
    '[file:size = 1 OR EXISTS process:name]',
]

NEEDS_MANUAL_PATTERNS = [
    '([a:b = \'1\'] WITHIN 1 SECONDS WITHIN 2 SECONDS)',
    '([a:b = \'1\'] REPEATS 2 TIMES REPEATS 3 TIMES)',
    '[a:b = \'1\'] START t\'2016-06-01T01:30:00Z\' STOP t\'2016-06-01T02:20:00Z\' '
    'START t\'2016-06-01T03:30:00Z\' STOP t\'2016-06-01T04:20:00Z\'',
]

# --- Control samples: identical behaviour on both sides -------------------

COMPATIBLE_PATTERNS = [
    '[file:size = 1280]',
    '[ipv4addr:value ISSUBSET \'192.168.0.1/24\']',
    '[foo:bar=1] REPEATS 9 TIMES',
    '[file:name MATCHES \'x\'] AND [file:size > 1] WITHIN 5 SECONDS',
]

INVALID_PATTERNS = [
    '[file:size = ]',                       # grammar error both
    '[file:hashes.\'SHA-256\' = \'f00\']',  # object constraint both
    'file:size = 1280',                     # missing brackets both
]


@pytest.mark.parametrize('pattern', V21_ONLY_PATTERNS)
def test_v21_only_classification(pattern):
    result = check_pattern(pattern)
    assert result.status == V21_ONLY
    assert result.v20_valid is False
    assert result.v21_valid is True
    assert result.v20_errors and not result.v21_errors
    assert any('EXISTS' in reason for reason in result.reasons)


@pytest.mark.parametrize('pattern', NEEDS_MANUAL_PATTERNS)
def test_needs_manual_review_classification(pattern):
    result = check_pattern(pattern)
    assert result.status == NEEDS_MANUAL_REVIEW
    assert result.v20_valid is True
    assert result.v21_valid is False
    assert not result.v20_errors and result.v21_errors
    assert any('qualifier' in reason for reason in result.reasons)


@pytest.mark.parametrize('pattern', COMPATIBLE_PATTERNS)
def test_compatible_classification(pattern):
    result = check_pattern(pattern)
    assert result.status == COMPATIBLE
    assert result.v20_valid is True
    assert result.v21_valid is True
    assert result.v20_errors == []
    assert result.v21_errors == []
    assert result.reasons == []


@pytest.mark.parametrize('pattern', INVALID_PATTERNS)
def test_invalid_classification(pattern):
    result = check_pattern(pattern)
    assert result.status == INVALID
    assert result.v20_valid is False
    assert result.v21_valid is False
    assert result.v20_errors and result.v21_errors


def test_statuses_cover_all_four_matrix_cells():
    results = check_patterns(
        COMPATIBLE_PATTERNS + NEEDS_MANUAL_PATTERNS +
        V21_ONLY_PATTERNS + INVALID_PATTERNS
    )
    counts = summarize(results)
    assert counts[COMPATIBLE] == len(COMPATIBLE_PATTERNS)
    assert counts[NEEDS_MANUAL_REVIEW] == len(NEEDS_MANUAL_PATTERNS)
    assert counts[V21_ONLY] == len(V21_ONLY_PATTERNS)
    assert counts[INVALID] == len(INVALID_PATTERNS)
    assert sum(counts.values()) == len(results)


def test_real_parse_results_are_preserved():
    # The migration result must report exactly what each standalone validator
    # returns, so decisions can be audited against the genuine parse output.
    pattern = '([a:b = \'1\'] WITHIN 1 SECONDS WITHIN 2 SECONDS)'
    result = check_pattern(pattern)
    assert result.v20_errors == run_validator(pattern, stix_version='2.0')
    assert result.v21_errors == run_validator(pattern, stix_version='2.1')
    assert 'Duplicate qualifier type encountered: WITHIN' in result.v21_errors[0]


def test_original_text_is_preserved_verbatim():
    pattern = '  [file:size = 1280]  '
    result = check_pattern(pattern)
    assert result.pattern == pattern


def test_patterns_are_never_rewritten():
    # No field of the result may contain an altered/derived expression; only
    # the original text and parse metadata are exposed.
    pattern = '[EXISTS file:name]'
    data = result_to_dict(check_pattern(pattern))
    serialized = json.dumps(data)
    assert pattern in serialized
    assert 'EXISTS file:name' in serialized
    # No alternative (rewritten) form of the expression is offered.
    assert 'rewritten' not in serialized
    assert data['pattern'] == pattern


def test_file_like_input_is_supported():
    stream = io.StringIO('[file:size = 1]\n[EXISTS a:b]\n')
    result = check_pattern(stream)
    # readline() retains the trailing newline; the original text is kept as-is.
    assert result.pattern == '[file:size = 1]\n'
    assert result.status == COMPATIBLE


def test_read_patterns_skips_blank_lines():
    stream = io.StringIO('[file:size = 1]\n\n  \n[EXISTS a:b]\n')
    assert read_patterns(stream) == ['[file:size = 1]', '[EXISTS a:b]']


def test_text_report_contains_errors_and_original():
    results = check_patterns(['[file:size = ]', '[EXISTS a:b]'])
    report = render_text_report(results)
    assert 'STIX 2.0 -> 2.1 Pattern Migration Report' in report
    assert '[file:size = ]' in report
    assert 'STIX 2.0 parse result: FAIL' in report
    assert 'STIX 2.1 parse result: FAIL' in report
    assert "mismatched input ']'" in report
    # The v21_only entry keeps its real 2.0 error and a 2.1 PASS.
    assert 'v21_only' in report


def test_json_report_is_valid_and_keeps_both_results():
    results = check_patterns(['[file:size = 1280]', '[EXISTS a:b]'])
    payload = json.loads(render_json_report(results))
    assert payload['default_version'] == '2.1'
    assert payload['supported_versions'] == ['2.0', '2.1']
    assert len(payload['results']) == 2
    first = payload['results'][0]
    assert set(first['stix_2_0']) == {'valid', 'errors'}
    assert set(first['stix_2_1']) == {'valid', 'errors'}
    assert first['stix_2_0']['valid'] is True
    exists = payload['results'][1]
    assert exists['stix_2_0']['valid'] is False
    assert exists['stix_2_1']['valid'] is True
    assert exists['stix_2_0']['errors']  # real error retained


def test_cli_text_output(tmp_path, capsys):
    patterns_file = tmp_path / 'patterns.txt'
    patterns_file.write_text('[file:size = 1]\n[EXISTS a:b]\n')
    rc = main(['-f', str(patterns_file)])
    assert rc == 0
    out = capsys.readouterr().out
    assert 'Migration Report' in out
    assert 'compatible' in out and 'v21_only' in out


def test_cli_json_output(tmp_path, capsys):
    patterns_file = tmp_path / 'patterns.txt'
    patterns_file.write_text('[file:size = 1]\n')
    rc = main(['-f', str(patterns_file), '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['summary']['compatible'] == 1


def test_cli_writes_output_file(tmp_path):
    patterns_file = tmp_path / 'patterns.txt'
    out_file = tmp_path / 'report.txt'
    patterns_file.write_text('[file:size = 1]\n')
    rc = main(['-f', str(patterns_file), '-o', str(out_file)])
    assert rc == 0
    content = out_file.read_text()
    assert 'Migration Report' in content
    assert '[file:size = 1]' in content


def test_all_statuses_have_labels():
    for status in (COMPATIBLE, NEEDS_MANUAL_REVIEW, V21_ONLY, INVALID):
        assert status in migration.STATUS_LABELS
