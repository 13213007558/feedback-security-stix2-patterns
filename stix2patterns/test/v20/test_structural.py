"""
Test cases for the hierarchical structural view of STIX 2.0 patterns
(``Pattern.structure``).

STIX 2.0 shares the observation/comparison grammar with 2.1 but has no
``EXISTS`` property test; the version tag and the independently built parse
tree are the focus here.
"""
import pytest

from stix2patterns.exceptions import ParseException
from stix2patterns.inspector import INDEX_STAR
from stix2patterns.v20.pattern import Pattern


def _structure(pattern):
    return Pattern(pattern).structure()


def _leftmost(node):
    if node[u"type"] == u"comparison":
        return node
    return _leftmost(node[u"operands"][0])


def test_version_tag():
    structure = _structure(u"[foo:bar = 1]")
    assert structure[u"type"] == u"pattern"
    assert structure[u"stix_version"] == u"2.0"


def test_and_or_precedence_pair_is_distinguished():
    flat_a = Pattern(u"[a:b=1] AND [a:c=2] OR [a:d=3]").inspect()
    flat_b = Pattern(u"[a:b=1] AND ([a:c=2] OR [a:d=3])").inspect()
    assert flat_a.observation_ops == flat_b.observation_ops

    a = _structure(u"[a:b=1] AND [a:c=2] OR [a:d=3]")[u"observation"]
    b = _structure(u"[a:b=1] AND ([a:c=2] OR [a:d=3])")[u"observation"]

    assert a[u"operator"] == u"OR"
    assert a[u"operands"][0][u"operator"] == u"AND"

    assert b[u"operator"] == u"AND"
    assert b[u"operands"][1][u"expression"][u"operator"] == u"OR"
    assert a != b


def test_followedby_qualifier_ownership_pair_is_distinguished():
    pattern_a = u"([a:b=1] OR [a:c=2]) FOLLOWEDBY [a:d=3] WITHIN 5 SECONDS"
    pattern_b = u"[a:b=1] OR ([a:c=2] FOLLOWEDBY [a:d=3] WITHIN 5 SECONDS)"

    assert Pattern(pattern_a).inspect().qualifiers == \
        Pattern(pattern_b).inspect().qualifiers

    a = _structure(pattern_a)[u"observation"]
    b = _structure(pattern_b)[u"observation"]

    assert a[u"operator"] == u"FOLLOWEDBY"
    assert [q[u"qualifier"]
            for q in a[u"operands"][1][u"qualifiers"]] == [u"WITHIN"]

    assert b[u"operator"] == u"OR"
    group_followedby = b[u"operands"][1][u"expression"]
    assert group_followedby[u"operator"] == u"FOLLOWEDBY"
    assert [q[u"qualifier"]
            for q in group_followedby[u"operands"][1][u"qualifiers"]] == \
        [u"WITHIN"]
    assert a != b


def test_in_bracket_parentheses_pair_is_distinguished():
    a = _structure(u"[a:b=1 OR a:c=2 AND a:d=3]")[u"observation"][u"expression"]
    b = _structure(u"[(a:b=1 OR a:c=2) AND a:d=3]")[u"observation"][u"expression"]

    assert a[u"operator"] == u"OR"
    assert a[u"operands"][1][u"operator"] == u"AND"

    assert b[u"operator"] == u"AND"
    group = b[u"operands"][0]
    assert group[u"grouped"] is True
    assert group[u"operands"][0][u"operator"] == u"OR"
    assert a != b


def test_qualifiers_attach_to_owning_observation():
    pattern = (
        u"([a:b=1] START t'1932-11-12T15:42:15Z' STOP t'1964-10-23T21:12:26Z' "
        u"AND [a:c=2]) WITHIN 22 SECONDS OR [a:d=3] REPEATS 31 TIMES"
    )
    root = _structure(pattern)[u"observation"]
    assert root[u"operator"] == u"OR"

    left_group = root[u"operands"][0]
    assert [q[u"qualifier"]
            for q in left_group[u"qualifiers"]] == [u"WITHIN"]

    start_stop = left_group[u"expression"][u"operands"][0] \
        [u"qualifiers"][0]
    assert start_stop[u"qualifier"] == u"START_STOP"
    assert start_stop[u"start_time"] == u"t'1932-11-12T15:42:15Z'"
    assert start_stop[u"stop_time"] == u"t'1964-10-23T21:12:26Z'"

    assert root[u"operands"][1][u"qualifiers"][0][u"qualifier"] == u"REPEATS"


def test_repeated_qualifiers_are_both_retained():
    # STIX 2.0 allows stacking REPEATS qualifiers; the flat view loses the
    # ordering/ownership while the structural view keeps both.
    pattern = u"[foo:bar = 1] REPEATS 1 TIMES REPEATS 2 TIMES"
    observation = _structure(pattern)[u"observation"]
    qualifiers = observation[u"qualifiers"]

    assert [q[u"qualifier"] for q in qualifiers] == [u"REPEATS", u"REPEATS"]
    assert [q[u"value"] for q in qualifiers] == [u"1", u"2"]
    # The positions differ even though the qualifier type repeats.
    assert qualifiers[0][u"position"] != qualifiers[1][u"position"]


@pytest.mark.parametrize(u"pattern,operator,value,negated", [
    (u"[a:b != 1]", u"!=", u"1", False),
    (u"[a:b NOT > 3]", u">", u"3", True),
    (u"[a:b IN (1, 2, 3)]", u"IN", u"(1,2,3)", False),
    (u"[a:b NOT LIKE 'p%']", u"LIKE", u"'p%'", True),
    (u"[a:b MATCHES 'abc']", u"MATCHES", u"'abc'", False),
    (u"[a:b NOT ISSUBSET 'x']", u"ISSUBSET", u"'x'", True),
    (u"[a:b ISSUPERSET 'x']", u"ISSUPERSET", u"'x'", False),
])
def test_comparison_operators(pattern, operator, value, negated):
    expression = _structure(pattern)[u"observation"][u"expression"]
    assert expression[u"operator"] == operator
    assert expression[u"value"] == value
    assert expression[u"negated"] is negated


def test_exists_is_not_supported():
    # The 2.0 grammar rejects the 2.1-only EXISTS test at parse time.
    with pytest.raises(ParseException):
        Pattern(u"[EXISTS a:b]")


def test_object_path_components():
    pattern = u"[obj-type:a.b[1][*][-1].'c-d' = 1]"
    object_path = _structure(pattern)[u"observation"][u"expression"] \
        [u"object_path"]
    assert object_path[u"object_type"] == u"obj-type"
    assert object_path[u"path"] == [u"a", u"b", 1, INDEX_STAR, -1, u"c-d"]


def test_position_points_back_at_source_text():
    pattern = u"[foo:bar = 1]"
    position = _structure(pattern)[u"observation"][u"expression"][u"position"]
    assert pattern[position[u"start"]:position[u"end"]] == u"foo:bar = 1"


def test_flat_inspect_output_is_unchanged():
    pattern = u"[foo:bar=1] AND [foo:baz > 25.2]"
    data = Pattern(pattern).inspect()
    assert data.observation_ops == {u"AND"}
    assert data.qualifiers == set()
    assert data.comparisons == {
        u"foo": [([u"bar"], u"=", u"1"), ([u"baz"], u">", u"25.2")],
    }

    # Building the structural view must not mutate the flat view data.
    _structure(pattern)
    assert Pattern(pattern).inspect() == data
