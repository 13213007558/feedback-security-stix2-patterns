"""
STIX 2.0 -> 2.1 pattern migration compatibility checking.

This module is the library-level entry point for the move from the STIX 2.0
patterning grammar to the 2.1 grammar.  Every input pattern is independently
validated against *both* specifications and the two real parse results are
retained so a migration decision can be audited line by line.

Design constraints (do not violate these):

* The two grammars differ only in a small number of places (most notably the
  v2.1-only ``EXISTS`` operator and the v2.1 duplicate-qualifier constraint).
  Classification is therefore driven entirely by the genuine results returned
  by the v2.0 and v2.1 validators -- never by guessing from the text.
* Patterns are never rewritten.  Some textual changes (for example removing a
  qualifier) would alter what a pattern detects, so this module only reports
  and advises; it never produces a "migrated" expression.
* An explicitly supplied, unsupported version is an error, never a silent
  fallback.
"""

import argparse
import collections
import json

from . import DEFAULT_VERSION, SUPPORTED_VERSIONS
from .exceptions import UnknownSTIXVersionError
from .validator import resolve_stix_version, run_validator

# Migration statuses.  These are plain string constants rather than an enum so
# they serialise directly to JSON and are easy to match in calling code.
#
# The statuses map one-to-one onto the four cells of the (2.0 valid?) x
# (2.1 valid?) result matrix, so every possible pair of real parse outcomes has
# exactly one meaning:
#
#   2.0 valid + 2.1 valid -> COMPATIBLE (migrate as-is)
#   2.0 valid + 2.1 FAIL  -> NEEDS_MANUAL_REVIEW (regression under 2.1)
#   2.0 FAIL  + 2.1 valid -> V21_ONLY (already a 2.1-only construct)
#   2.0 FAIL  + 2.1 FAIL  -> INVALID (broken under both)
COMPATIBLE = 'compatible'
NEEDS_MANUAL_REVIEW = 'needs_manual_review'
V21_ONLY = 'v21_only'
INVALID = 'invalid'

#: Human-readable one-line explanation for each status.
STATUS_LABELS = {
    COMPATIBLE: 'Valid under both 2.0 and 2.1 - migrate as-is',
    NEEDS_MANUAL_REVIEW: 'Valid under 2.0 but rejected under 2.1 - manual change required',
    V21_ONLY: 'Rejected under 2.0 but valid under 2.1 - already a 2.1-only construct',
    INVALID: 'Rejected under both 2.0 and 2.1 - fix the pattern itself',
}

# Advisory detail for the known, genuine cross-version differences.  These only
# annotate the real validator errors; they never transform the expression.
_REASON_EXISTS = (
    "Uses the v2.1-only EXISTS operator, which the 2.0 grammar does not know. "
    "It is already valid 2.1, so no change is required for the 2.1 target; do "
    "not attempt to back-port it to 2.0."
)
_REASON_DUPLICATE_QUALIFIER = (
    "Applies the same qualifier type (WITHIN, REPEATS or START/STOP) more than "
    "once to one observation expression. 2.1 forbids duplicate qualifier types; "
    "restructure the qualifiers manually so the intended detection semantics are preserved."
)
_REASON_V21_UNKNOWN = (
    "Rejected by the 2.1 grammar/object constraints even though it parsed under "
    "2.0. Inspect the 2.1 error below and adjust the expression manually."
)
_REASON_V20_UNKNOWN = (
    "Rejected by the 2.0 grammar but accepted under 2.1. This relies on a "
    "2.1-only feature; keep it as a 2.1 pattern and do not rewrite it by hand."
)


PatternMigrationResult = collections.namedtuple(
    'PatternMigrationResult',
    [
        'pattern',          # original, untouched pattern text
        'status',           # one of the STATUS_* constants
        'v20_valid',        # bool: passed the 2.0 validator
        'v21_valid',        # bool: passed the 2.1 validator
        'v20_errors',       # list[str]: real 2.0 parse/validation errors
        'v21_errors',       # list[str]: real 2.1 parse/validation errors
        'reasons',          # list[str]: advisory notes (no rewriting)
    ],
)


def _classify(v20_valid, v21_valid, v20_errors, v21_errors):
    """
    Decide the migration status from the two genuine validation results and
    attach advisory reasons.  Classification follows the 2x2 validation
    matrix exactly; pattern text is only consulted indirectly via the real
    error messages, and nothing is ever rewritten.
    """
    if v20_valid and v21_valid:
        return COMPATIBLE, []

    if not v20_valid and not v21_valid:
        return INVALID, []

    reasons = []

    if v20_valid and not v21_valid:
        # Accepted by 2.0, rejected by 2.1 -> a genuine migration regression.
        joined_21 = " ".join(v21_errors)
        if 'Duplicate qualifier type' in joined_21:
            reasons.append(_REASON_DUPLICATE_QUALIFIER)
        else:
            reasons.append(_REASON_V21_UNKNOWN)
        return NEEDS_MANUAL_REVIEW, reasons

    # 2.0 rejected it but 2.1 accepts it -> a 2.1-only feature.
    joined_20 = " ".join(v20_errors)
    if 'EXISTS' in joined_20:
        reasons.append(_REASON_EXISTS)
    else:
        reasons.append(_REASON_V20_UNKNOWN)
    return V21_ONLY, reasons


def check_pattern(pattern):
    """
    Run a single pattern through both the STIX 2.0 and 2.1 validators and
    return a :class:`PatternMigrationResult` preserving both real results.

    :param pattern: A STIX pattern string.
    :return: A populated :class:`PatternMigrationResult`.
    """
    pattern_text = pattern if isinstance(pattern, str) else pattern.readline()

    v20_errors = run_validator(pattern_text, stix_version='2.0')
    v21_errors = run_validator(pattern_text, stix_version='2.1')

    v20_valid = not v20_errors
    v21_valid = not v21_errors

    status, reasons = _classify(v20_valid, v21_valid, v20_errors, v21_errors)

    return PatternMigrationResult(
        pattern=pattern_text,
        status=status,
        v20_valid=v20_valid,
        v21_valid=v21_valid,
        v20_errors=list(v20_errors),
        v21_errors=list(v21_errors),
        reasons=reasons,
    )


def check_patterns(patterns):
    """
    Validate an iterable of patterns against both versions.

    :param patterns: An iterable of STIX pattern strings.
    :return: A list of :class:`PatternMigrationResult`, one per input pattern
        and in input order.
    """
    return [check_pattern(pattern) for pattern in patterns]


def summarize(results):
    """
    Produce a count of results by migration status.

    :param results: An iterable of :class:`PatternMigrationResult`.
    :return: An ``OrderedDict`` keyed by the status constants.
    """
    counts = collections.OrderedDict((s, 0) for s in
                                     (COMPATIBLE, NEEDS_MANUAL_REVIEW, V21_ONLY, INVALID))
    for result in results:
        counts[result.status] += 1
    return counts


def result_to_dict(result):
    """Convert one result to a JSON-serialisable dict (original text kept)."""
    return {
        'pattern': result.pattern,
        'status': result.status,
        'status_label': STATUS_LABELS[result.status],
        'stix_2_0': {
            'valid': result.v20_valid,
            'errors': result.v20_errors,
        },
        'stix_2_1': {
            'valid': result.v21_valid,
            'errors': result.v21_errors,
        },
        'reasons': result.reasons,
    }


def render_text_report(results):
    """
    Render a plain-text, offline migration report.

    Each entry keeps the original pattern verbatim and the genuine error list
    from both validators so every migration decision can be checked by hand.
    """
    counts = summarize(results)
    lines = []
    lines.append("STIX 2.0 -> 2.1 Pattern Migration Report")
    lines.append("=" * 60)
    lines.append("Total patterns checked: %d" % len(results))
    lines.append("  %s: %d" % (STATUS_LABELS[COMPATIBLE], counts[COMPATIBLE]))
    lines.append("  %s: %d" % (
        STATUS_LABELS[NEEDS_MANUAL_REVIEW], counts[NEEDS_MANUAL_REVIEW]))
    lines.append("  %s: %d" % (STATUS_LABELS[V21_ONLY], counts[V21_ONLY]))
    lines.append("  %s: %d" % (STATUS_LABELS[INVALID], counts[INVALID]))
    lines.append("")
    lines.append(
        "No expressions are rewritten. Review 'needs_manual_review' items by "
        "hand using the real errors below.")
    lines.append("")

    for index, result in enumerate(results, start=1):
        lines.append("-" * 60)
        lines.append("[%d] STATUS: %s" % (index, result.status))
        lines.append("    %s" % STATUS_LABELS[result.status])
        lines.append("    Original pattern:")
        lines.append("      %s" % result.pattern)
        lines.append("    STIX 2.0 parse result: %s"
                     % ("PASS" if result.v20_valid else "FAIL"))
        for err in result.v20_errors:
            lines.append("      - %s" % err)
        lines.append("    STIX 2.1 parse result: %s"
                     % ("PASS" if result.v21_valid else "FAIL"))
        for err in result.v21_errors:
            lines.append("      - %s" % err)
        if result.reasons:
            lines.append("    Migration guidance:")
            for reason in result.reasons:
                lines.append("      * %s" % reason)
        lines.append("")

    return "\n".join(lines)


def render_json_report(results):
    """Render a structured JSON migration report (original text kept)."""
    payload = {
        'default_version': DEFAULT_VERSION,
        'supported_versions': list(SUPPORTED_VERSIONS),
        'summary': dict(summarize(results)),
        'results': [result_to_dict(result) for result in results],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def read_patterns(file):
    """Read one pattern per non-empty line from an open text file object."""
    return [line.strip() for line in file if line.strip()]


def main(argv=None):
    """
    Offline command-line entry point that emits a migration compatibility
    report.  Reads patterns from a file (one per line).
    """
    parser = argparse.ArgumentParser(
        prog='stix2-pattern-migration',
        description='Check STIX patterns for 2.0 -> 2.1 migration '
                    'compatibility. Patterns are validated against both '
                    'versions and never rewritten.')
    parser.add_argument('-f', '--file', required=True,
                        type=argparse.FileType('r'),
                        help='File containing one STIX pattern per line.')
    parser.add_argument('--json', action='store_true',
                        help='Emit a structured JSON report instead of text.')
    parser.add_argument('-o', '--output',
                        help='Write the report to this path instead of stdout.')
    args = parser.parse_args(argv)

    # Touch the resolver so an explicit/default version mismatch would still
    # surface as a clear error; supported versions are reported regardless.
    try:
        resolve_stix_version(DEFAULT_VERSION)
    except UnknownSTIXVersionError as exc:  # pragma: no cover - defensive
        parser.error(str(exc))

    try:
        patterns = read_patterns(args.file)
        results = check_patterns(patterns)
        report = render_json_report(results) if args.json \
            else render_text_report(results)
    finally:
        args.file.close()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as out:
            out.write(report)
            out.write("\n")
    else:
        print(report)

    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
