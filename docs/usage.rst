Usage
=====

The STIX Pattern Validator provides an executable script (``validate-patterns``)
in addition to being an importable Python library.

The ``validate-patterns`` script accepts patterns from either direct user input
or a file passed as an option.

From Python Code
----------------

The ``run_validator`` function can be called on any Python string. It returns a
list of errors encountered while parsing the pattern.

.. code:: python

    from stix2patterns.validator import run_validator

    pattern = "[file-object:hashes.md5 = '79054025255fb1a26e4bc422aef54eb4']"
    errors = run_validator(pattern)

User Input
----------

When prompted, enter a pattern to validate and press enter. The validator will
supply whether the pattern has passed or failed. If the pattern fails the test,
the validator will supply where the first syntax error occurred. The validator
will continue to prompt for patterns until Ctrl-C is pressed. Example:

.. code:: bash

    $ validate-patterns

    Enter a pattern to validate: [file-object:hashes.md5 = '79054025255fb1a26e4bc422aef54eb4']

    PASS: [file-object:hashes.md5 = '79054025255fb1a26e4bc422aef54eb4']

File Input
----------

.. code:: bash

    $ validate-patterns -f <path_to_file>

Use <path\_to\_file> to specify the path to a file containing a set of patterns
to validate. Each pattern must be on a separate line of the file so that the
validator may determine where the pattern begins and ends. The validator will
supply the PASS/FAIL result of each pattern.

Choosing a STIX Version
-----------------------

The library default is the latest supported STIX 2.X version
(``stix2patterns.DEFAULT_VERSION``, currently ``'2.1'``). Pass an explicit
``stix_version`` to validate against a different one:

.. code:: python

    from stix2patterns.validator import run_validator

    run_validator("[file:size = 1280]", stix_version='2.0')
    run_validator("[file:size = 1280]", stix_version='2.1')

An explicit version is always honoured; it is never overridden by the default.
Requesting a version the library does not support raises
``stix2patterns.exceptions.UnknownSTIXVersionError`` instead of silently
falling back to another version. The supported versions are listed in
``stix2patterns.SUPPORTED_VERSIONS``. Pass ``None`` (or omit the argument) to
use the default.

Migrating Patterns from 2.0 to 2.1
----------------------------------

The ``stix2patterns.migration`` module is the library-level entry point for the
move from the STIX 2.0 to the 2.1 patterning grammar. Every input pattern is
validated against **both** specifications and the two real parse results are
retained so each migration decision can be audited individually.

.. code:: python

    from stix2patterns.migration import check_pattern

    result = check_pattern("[EXISTS file:name]")
    print(result.status)       # 'v21_only'
    print(result.v20_errors)   # genuine 2.0 parser errors
    print(result.v21_errors)   # []  (valid under 2.1)

Each result has one of four statuses, corresponding to the four possible
combinations of the two validation outcomes:

* ``compatible`` -- valid under both 2.0 and 2.1; migrate as-is.
* ``needs_manual_review`` -- valid under 2.0 but rejected under 2.1 (for
  example a duplicate qualifier type, which 2.1 forbids); change by hand.
* ``v21_only`` -- rejected under 2.0 but valid under 2.1 (for example the
  2.1-only ``EXISTS`` operator); already a valid 2.1 pattern.
* ``invalid`` -- rejected under both versions; fix the pattern itself.

The checker never rewrites an expression. Some textual edits (such as removing a
qualifier) would change what a pattern detects, so the module only reports the
genuine errors from both validators and, where the difference is a known one,
adds advisory guidance. The original pattern text is always preserved verbatim.

An offline, human-readable report (or a structured JSON report) can be produced
from a file containing one pattern per line:

.. code:: bash

    $ stix2-pattern-migration -f patterns.txt
    $ stix2-pattern-migration -f patterns.txt --json -o migration_report.json

The same report is available programmatically via
``render_text_report`` / ``render_json_report``. It runs entirely offline and
contains, for every pattern: the original text, the real 2.0 and 2.1
PASS/FAIL results with their full error messages, the status, and any guidance.
