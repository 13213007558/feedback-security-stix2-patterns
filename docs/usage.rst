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

Inspecting a Pattern
--------------------

A compiled :class:`~stix2patterns.v21.pattern.Pattern` offers two read-only
views. ``inspect()`` keeps the existing flat summary of the comparisons,
observation operators and qualifiers in the pattern. For static analysis that
needs the actual structure, ``structure()`` returns a hierarchical,
version-tagged object which mirrors the parse tree:

* the nesting of observation-level ``AND``/``OR``/``FOLLOWEDBY`` and the
  in-bracket comparison expressions (including parentheses), so precedence is
  taken from the parse tree rather than reconstructed;
* each attribute path and comparison operator/value;
* the observation expression that every ``WITHIN``/``REPEATS``/
  ``START ... STOP`` qualifier belongs to;
* a ``position`` (line, column and character offsets) on every node, so a
  reported problem can be pointed back at the original expression.

The result is built only from ``dict``/``list``/scalar values, so it can be
serialised directly. It is a structural view and does not evaluate the pattern
against data.

.. code:: python

    from stix2patterns.v21.pattern import Pattern

    # STIX 2.0 is available via stix2patterns.v20.pattern.Pattern and stamps
    # its result with stix_version "2.0".
    pattern = Pattern("[a:b = 1] AND ([a:c = 2] OR [a:d = 3])")
    structure = pattern.structure()
    print(structure["stix_version"])        # "2.1"
    root = structure["observation"]
    print(root["operator"])                 # "AND"
    print(root["operands"][1]["expression"]["operator"])  # "OR"

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
