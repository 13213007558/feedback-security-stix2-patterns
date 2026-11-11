"""
Regression tests for STIX pattern lexer/parser error handling.

The gateway treats an empty error list from the pattern validator as
"pattern acceptable".  These tests make sure malformed input can never be
silently recovered past by the lexer (e.g. an offending character skipped, a
truncated token ignored, or trailing tokens dropped) to leave a legal-looking
pattern behind.  They also pin the three public entry points (the version
dispatch ``validate``/``run_validator`` and the ``Pattern`` compiler) to make
identical accept/reject decisions, and confirm failures are returned as
structured error strings (with line/column) rather than only printed to
stderr.
"""
import re

import pytest

from antlr4.atn.LexerATNSimulator import LexerATNSimulator
from antlr4.error.Errors import LexerNoViableAltException

from stix2patterns.exceptions import ParseException
from stix2patterns.validator import run_validator, validate
from stix2patterns.v20.pattern import Pattern as Pattern20
from stix2patterns.v21.pattern import Pattern as Pattern21

VERSIONS = ("2.0", "2.1")
PATTERN_CLASSES = {"2.0": Pattern20, "2.1": Pattern21}
POSITION_RE = re.compile(r"line \d+:\d+")


def _pattern_rejects(pattern_cls, pattern_str):
    """True if the Pattern compiler refuses the input."""
    try:
        pattern_cls(pattern_str)
    except ParseException:
        return True
    return False


# --- Malformed input that must never validate ---------------------------------

ILLEGAL_CHAR_CASES = [
    "[file:name = @]",
    "[file:name = `x`]",
    "[file:na\x00me = 1]",
    "[file:name = $]",
    '[file:name = "x"]',
    "[file:name = a&b]",
    "[file:name = ~]",
    "[file:name = ?]",
    "[file:name = ;]",
    # Illegal code point used where an identifier/operator is expected.
    "[fïle:size = 1]",
    # BOM in the middle of an object path is not whitespace.
    "[file:name﻿ = 1]",
]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str", ILLEGAL_CHAR_CASES)
def test_illegal_characters_rejected(version, pattern_str):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True
    )
    assert passed is False
    assert errors, "a lexer/parser failure must produce an error string"
    assert POSITION_RE.search(errors[0]), errors
    assert _pattern_rejects(PATTERN_CLASSES[version], pattern_str)


TRUNCATED_STRING_CASES = [
    "[file:name = 'abc]",
    "[file:name = 'abc",
    "[file:name = 'abc\\",
    # An escape sequence which is never closed by a terminating quote.
    "[file:name = 'abc\\'",
]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str", TRUNCATED_STRING_CASES)
def test_truncated_strings_rejected(version, pattern_str):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True
    )
    assert passed is False
    assert errors
    assert POSITION_RE.search(errors[0]), errors
    assert _pattern_rejects(PATTERN_CLASSES[version], pattern_str)


STRING_ESCAPE_CASES = [
    # Only the quote and the backslash are valid escape targets.
    ("[file:name = '\\q']", False),
    ("[file:name = 'a\\nb']", False),
    ("[file:name = 'a\\tb']", False),
    # A bare backslash outside of a string is itself an illegal character.
    ("[file:name = \\ ]", False),
    # Valid escapes and literal backslashes must not be over-blocked.
    ("[file:name = 'it\\'s']", True),
    ("[file:name = 'a\\\\b']", True),
    (r"[win-registry-key:key = 'hkey_local_machine\\foo\\bar']", True),
]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str,should_pass", STRING_ESCAPE_CASES)
def test_string_escapes(version, pattern_str, should_pass):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True
    )
    assert passed is should_pass, (pattern_str, errors)
    if should_pass:
        assert errors == []
        PATTERN_CLASSES[version](pattern_str)
    else:
        assert errors
        assert POSITION_RE.search(errors[0]), errors
        assert _pattern_rejects(PATTERN_CLASSES[version], pattern_str)


BINARY_LITERAL_CASES = [
    # Truncated (no closing quote) binary literals.
    ("[artifact:payload_bin = b'abc]", False),
    ("[artifact:payload_bin = b'abc", False),
    # Character outside the base64 alphabet.
    ("[artifact:payload_bin = b'====']", False),
    ("[artifact:payload_bin = b'not base64!']", False),
    # Well-formed base64 must keep passing.
    ("[artifact:payload_bin = b'dGhpcyBpcyBhIHRlc3Q=']", True),
]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str,should_pass", BINARY_LITERAL_CASES)
def test_binary_literals(version, pattern_str, should_pass):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True
    )
    assert passed is should_pass, (pattern_str, errors)
    if should_pass:
        assert errors == []
        PATTERN_CLASSES[version](pattern_str)
    else:
        assert errors
        assert POSITION_RE.search(errors[0]), errors
        assert _pattern_rejects(PATTERN_CLASSES[version], pattern_str)


HEX_LITERAL_CASES = [
    # Truncated (no closing quote) hex literals.
    ("[file:foo = h'41]", False),
    ("[file:foo = h'41", False),
    # Non-hex content.
    ("[file:foo = h'ZZ']", False),
    ("[file:foo = h'4g']", False),
    # Odd nibble count is not a valid byte sequence.
    ("[file:foo = h'4']", False),
    # Well-formed hex must keep passing.
    ("[file:foo = h'4142']", True),
    ("[file:foo = h'']", True),
]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str,should_pass", HEX_LITERAL_CASES)
def test_hex_literals(version, pattern_str, should_pass):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True
    )
    assert passed is should_pass, (pattern_str, errors)
    if should_pass:
        assert errors == []
        PATTERN_CLASSES[version](pattern_str)
    else:
        assert errors
        assert POSITION_RE.search(errors[0]), errors
        assert _pattern_rejects(PATTERN_CLASSES[version], pattern_str)


ILLEGAL_UNICODE_POSITION_CASES = [
    # The reported column must point at the offending code point.
    ("[fïle:size = 1]", 2),
    ("[file:size = 1] é", 16),
    ("[file:name﻿ = 1]", 10),
]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str,column", ILLEGAL_UNICODE_POSITION_CASES)
def test_illegal_unicode_reports_position(version, pattern_str, column):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True
    )
    assert passed is False
    match = POSITION_RE.search(errors[0])
    assert match, errors
    line, reported_column = match.group(0).split(" ")[1].split(":")
    assert line == "1"
    assert int(reported_column) == column
    assert _pattern_rejects(PATTERN_CLASSES[version], pattern_str)


TRAILING_TOKEN_CASES = [
    "[file:size = 1] GARBAGE",
    "[file:size = 1] @",
    "[file:size = 1] ]",
    "[file:size = 1] '",
    "[file:size = 1] #",
    "[file:size = 1] 123",
]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str", TRAILING_TOKEN_CASES)
def test_trailing_tokens_rejected(version, pattern_str):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True
    )
    assert passed is False
    assert errors
    # The start rule ends in EOF, so junk after a valid pattern is an
    # "extraneous input ... expecting <EOF>" parse failure.
    assert "expecting <EOF>" in errors[0], errors
    assert POSITION_RE.search(errors[0]), errors
    assert _pattern_rejects(PATTERN_CLASSES[version], pattern_str)


# --- Cross entry-point consistency --------------------------------------------

CONSISTENCY_CASES = (
    ILLEGAL_CHAR_CASES
    + TRUNCATED_STRING_CASES
    + [case for case, _ in STRING_ESCAPE_CASES]
    + [case for case, _ in BINARY_LITERAL_CASES]
    + [case for case, _ in HEX_LITERAL_CASES]
    + [case for case, _ in ILLEGAL_UNICODE_POSITION_CASES]
    + TRAILING_TOKEN_CASES
    + [
        "[file:size = 1280]",
        "[file:name = 'my_file_name']",
        "[artifact:payload_bin = b'dGhpcyBpcyBhIHRlc3Q=']",
        "[file:foo = h'414243']",
        "[x:created = t'2018-03-22T12:11:14.1Z']",
        "[a:b = 1] AND [c:d = 'x'] WITHIN 5 SECONDS",
    ]
)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str", CONSISTENCY_CASES)
def test_entry_points_agree(version, pattern_str):
    validator_passed = validate(pattern_str, stix_version=version)
    validator_errors = run_validator(pattern_str, stix_version=version)
    pattern_passed = not _pattern_rejects(
        PATTERN_CLASSES[version], pattern_str
    )

    # validate() must agree with the underlying run_validator() result.
    assert validator_passed is (len(validator_errors) == 0)
    # The dispatch entry and the Pattern compiler must decide identically.
    assert validator_passed is pattern_passed, (version, pattern_str)


# --- Failures are returned, not merely printed --------------------------------

@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("pattern_str", ILLEGAL_CHAR_CASES[:3])
def test_errors_not_only_on_stderr(version, pattern_str, capsys):
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True, print_errs=False
    )
    captured = capsys.readouterr()
    assert passed is False
    assert errors, "the failure must be surfaced in the structured result"
    # With printing disabled nothing should be emitted at all.
    assert captured.err == ""
    assert captured.out == ""


@pytest.fixture
def lexer_no_viable(monkeypatch):
    """
    Force the lexer to raise a LexerNoViableAltException once for an interior
    character.  ANTLR's default recovery skips that character and continues
    tokenizing, so without a lexer error listener the remaining tokens form a
    legal pattern and the input would be wrongly accepted.
    """
    junk = ord("@")
    state = {"fired": False}
    original_match = LexerATNSimulator.match

    def patched_match(self, inp, mode):
        if inp.LA(1) == junk and not state["fired"]:
            state["fired"] = True
            raise LexerNoViableAltException(self.recog, inp, None, None)
        return original_match(self, inp, mode)

    monkeypatch.setattr(LexerATNSimulator, "match", patched_match)
    return "[file:size " + chr(junk) + " = 1280]"


@pytest.mark.parametrize("version", VERSIONS)
def test_lexer_recovery_error_is_failure(version, lexer_no_viable, capsys):
    pattern_str = lexer_no_viable
    passed, errors = validate(
        pattern_str, stix_version=version, ret_errs=True, print_errs=False
    )
    captured = capsys.readouterr()
    assert passed is False
    assert errors == [
        "FAIL: Error found at line 1:11. token recognition error at: '@'"
    ]
    assert captured.err == ""
    assert captured.out == ""


@pytest.mark.parametrize("version", VERSIONS)
def test_pattern_compiler_rejects_lexer_recovery(version, lexer_no_viable):
    with pytest.raises(ParseException) as exc_info:
        PATTERN_CLASSES[version](lexer_no_viable)
    message = str(exc_info.value)
    assert "1:11" in message
    assert "token recognition error at: '@'" in message
