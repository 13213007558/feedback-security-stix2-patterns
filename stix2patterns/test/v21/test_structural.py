"""
Test cases for the hierarchical structural view of STIX 2.1 patterns
(``Pattern.structure``).

The emphasis is on patterns that the flat ``inspect`` result cannot tell
apart: pairs that differ only in parenthesis placement or in which
observation expression a qualifier belongs to.
"""
import pytest

from stix2patterns.inspector import INDEX_STAR
from stix2patterns.v21.pattern import Pattern


def _structure(pattern):
    return Pattern(pattern).structure()


def _leftmost(node):
    if node[u"type"] == u"comparison":
        return node
    return _leftmost(node[u"operands"][0])


def _find_observations(node):
    if node[u"type"] == u"observation":
        return [node]
    found = []
    for operand in node[u"operands"]:
        found.extend(_find_observations(operand))
    return found


def test_version_tag():
    structure = _structure(u"[foo:bar = 1]")
    assert structure[u"type"] == u"pattern"
    assert structure[u"stix_version"] == u"2.1"


def test_single_observation():
    structure = _structure(u"[foo:bar = 1]")
    observation = structure[u"observation"]

    assert observation[u"type"] == u"observation"
    assert observation[u"object_type"] == u"foo"
    assert observation[u"qualifiers"] == []

    comparison = observation[u"expression"]
    assert comparison[u"type"] == u"comparison"
    assert comparison[u"operator"] == u"="
    assert comparison[u"negated"] is False
    assert comparison[u"value"] == u"1"
    assert comparison[u"object_path"][u"object_type"] == u"foo"
    assert comparison[u"object_path"][u"path"] == [u"bar"]


def test_and_or_precedence_pair_is_distinguished():
    # Same three comparisons and same two operators; only the parentheses move.
    flat_a = Pattern(u"[a:b=1] AND [a:c=2] OR [a:d=3]").inspect()
    flat_b = Pattern(u"[a:b=1] AND ([a:c=2] OR [a:d=3])").inspect()
    # The flat view records the same operator set for both.
    assert flat_a.observation_ops == flat_b.observation_ops

    a = _structure(u"[a:b=1] AND [a:c=2] OR [a:d=3]")[u"observation"]
    b = _structure(u"[a:b=1] AND ([a:c=2] OR [a:d=3])")[u"observation"]

    # Default precedence: (A AND B) OR C
    assert a[u"type"] == u"observation_operator"
    assert a[u"operator"] == u"OR"
    assert a[u"operands"][0][u"operator"] == u"AND"
    assert a[u"operands"][1][u"type"] == u"observation"

    # Parentheses force: A AND (B OR C)
    assert b[u"type"] == u"observation_operator"
    assert b[u"operator"] == u"AND"
    grouped = b[u"operands"][1]
    assert grouped[u"type"] == u"observation"
    assert grouped[u"object_type"] is None
    assert grouped[u"expression"][u"operator"] == u"OR"

    # The two hierarchical structures therefore cannot be equal.
    assert a != b


def test_followedby_qualifier_ownership_pair_is_distinguished():
    # The WITHIN qualifier attaches to a different observation expression in
    # each pattern, although the flat qualifier/operator sets are identical.
    pattern_a = u"([a:b=1] OR [a:c=2]) FOLLOWEDBY [a:d=3] WITHIN 5 SECONDS"
    pattern_b = u"[a:b=1] OR ([a:c=2] FOLLOWEDBY [a:d=3] WITHIN 5 SECONDS)"

    flat_a = Pattern(pattern_a).inspect()
    flat_b = Pattern(pattern_b).inspect()
    assert flat_a.qualifiers == flat_b.qualifiers
    assert flat_a.observation_ops == flat_b.observation_ops

    a = _structure(pattern_a)[u"observation"]
    b = _structure(pattern_b)[u"observation"]

    # In (a), FOLLOWEDBY is the root and WITHIN belongs to its right operand.
    assert a[u"operator"] == u"FOLLOWEDBY"
    right_a = a[u"operands"][1]
    assert [q[u"qualifier"] for q in right_a[u"qualifiers"]] == [u"WITHIN"]
    assert right_a[u"qualifiers"][0][u"value"] == u"5"

    # In (b), OR is the root and WITHIN stays inside the parenthesised
    # FOLLOWEDBY group on its right side.
    assert b[u"operator"] == u"OR"
    group_b = b[u"operands"][1]
    assert group_b[u"expression"][u"operator"] == u"FOLLOWEDBY"
    inner_right = group_b[u"expression"][u"operands"][1]
    assert [q[u"qualifier"] for q in inner_right[u"qualifiers"]] == [u"WITHIN"]

    assert a != b


def test_in_bracket_parentheses_pair_is_distinguished():
    a = _structure(u"[a:b=1 OR a:c=2 AND a:d=3]")[u"observation"][u"expression"]
    b = _structure(u"[(a:b=1 OR a:c=2) AND a:d=3]")[u"observation"][u"expression"]

    # Default: b OR (c AND d)
    assert a[u"operator"] == u"OR"
    assert a[u"operands"][1][u"operator"] == u"AND"

    # Parentheses: (b OR c) AND d, with an explicit grouping node.
    assert b[u"operator"] == u"AND"
    group = b[u"operands"][0]
    assert group[u"grouped"] is True
    assert group[u"operator"] is None
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
    assert [q[u"qualifier"] for q in left_group[u"qualifiers"]] == [u"WITHIN"]
    within = left_group[u"qualifiers"][0]
    assert within[u"value"] == u"22"

    and_expr = left_group[u"expression"]
    assert and_expr[u"operator"] == u"AND"
    start_stop_owner = and_expr[u"operands"][0]
    start_stop = start_stop_owner[u"qualifiers"][0]
    assert start_stop[u"qualifier"] == u"START_STOP"
    assert start_stop[u"start_time"] == u"t'1932-11-12T15:42:15Z'"
    assert start_stop[u"stop_time"] == u"t'1964-10-23T21:12:26Z'"

    repeats_owner = root[u"operands"][1]
    assert repeats_owner[u"qualifiers"][0][u"qualifier"] == u"REPEATS"
    assert repeats_owner[u"qualifiers"][0][u"value"] == u"31"


def test_qualifier_order_is_preserved():
    pattern = u"[a:b=1] REPEATS 2 TIMES WITHIN 10 SECONDS"
    observation = _structure(pattern)[u"observation"]
    assert [q[u"qualifier"] for q in observation[u"qualifiers"]] == \
        [u"REPEATS", u"WITHIN"]


@pytest.mark.parametrize(u"pattern,operator,value,negated", [
    (u"[a:b != 1]", u"!=", u"1", False),
    (u"[a:b NOT != 1]", u"!=", u"1", True),
    (u"[a:b > 2.5]", u">", u"2.5", False),
    (u"[a:b NOT < 3]", u"<", u"3", True),
    (u"[a:b IN (1, 2, 3)]", u"IN", u"(1,2,3)", False),
    (u"[a:b NOT IN ('x', 'y')]", u"IN", u"('x','y')", True),
    (u"[a:b LIKE 'p%']", u"LIKE", u"'p%'", False),
    (u"[a:b MATCHES 'abc']", u"MATCHES", u"'abc'", False),
    (u"[a:b ISSUBSET '1.2.3.4/16']", u"ISSUBSET", u"'1.2.3.4/16'", False),
    (u"[a:b NOT ISSUPERSET '1.2.3.4/16']", u"ISSUPERSET",
     u"'1.2.3.4/16'", True),
])
def test_comparison_operators(pattern, operator, value, negated):
    expression = _structure(pattern)[u"observation"][u"expression"]
    assert expression[u"operator"] == operator
    assert expression[u"value"] == value
    assert expression[u"negated"] is negated


def test_exists_is_version_21_only():
    positive = _structure(u"[EXISTS a:b]")[u"observation"][u"expression"]
    assert positive[u"operator"] == u"EXISTS"
    assert positive[u"value"] is None
    assert positive[u"negated"] is False

    negative = _structure(u"[NOT EXISTS a:b]")[u"observation"][u"expression"]
    assert negative[u"operator"] == u"EXISTS"
    assert negative[u"negated"] is True


def test_object_path_components():
    pattern = u"[obj-type:a.b[1][*][-1].'c-d' = 1]"
    comparison = _structure(pattern)[u"observation"][u"expression"]
    object_path = comparison[u"object_path"]

    assert object_path[u"object_type"] == u"obj-type"
    assert object_path[u"path"] == [
        u"a", u"b", 1, INDEX_STAR, -1, u"c-d",
    ]


def test_every_node_carries_position():
    structure = _structure(
        u"[a:b=1] AND ([a:c=2] OR [a:d=3]) WITHIN 5 SECONDS")

    def check(node):
        position = node[u"position"]
        assert set(position) == {u"line", u"column", u"start", u"end"}
        assert position[u"start"] < position[u"end"]
        if node[u"type"] in (u"observation_operator",
                             u"comparison_operator"):
            for operand in node[u"operands"]:
                check(operand)
        elif node[u"type"] == u"observation":
            check(node[u"expression"])
            for qualifier in node[u"qualifiers"]:
                check(qualifier)
        elif node[u"type"] == u"comparison":
            assert u"position" in node[u"object_path"]

    check(structure)
    check(structure[u"observation"])


def test_position_points_back_at_source_text():
    pattern = u"[foo:bar = 1]"
    comparison = _structure(pattern)[u"observation"][u"expression"]
    position = comparison[u"position"]
    # Slicing the original expression with the offsets yields the full test.
    assert pattern[position[u"start"]:position[u"end"]] == u"foo:bar = 1"

    root = _structure(u"[a:b=1] AND [a:c=2]")[u"observation"]
    leaf = _leftmost(root[u"operands"][0][u"expression"])
    # The leftmost leaf keeps the path of the first comparison.
    assert leaf[u"object_path"][u"path"] == [u"b"]


def test_observation_operand_order_matches_source():
    root = _structure(u"[a:b=1] FOLLOWEDBY [a:c=2]")[u"observation"]
    assert root[u"operator"] == u"FOLLOWEDBY"
    observations = _find_observations(root)
    paths = [
        _leftmost(o[u"expression"])[u"object_path"][u"path"]
        for o in observations
    ]
    assert paths == [[u"b"], [u"c"]]


def test_flat_inspect_output_is_unchanged():
    pattern = (
        u"[foo:bar=1 AND bar:foo NOT >33] REPEATS 12 TIMES OR "
        u"([baz:bar ISSUBSET '1234'] FOLLOWEDBY [baz:quux NOT LIKE 'a_cd'])"
    )
    data = Pattern(pattern).inspect()

    # The REPEATS qualifier applies to the first observation expression, whose
    # in-bracket AND is not an observation-level operator.
    assert data.observation_ops == {u"OR", u"FOLLOWEDBY"}
    assert data.qualifiers == {u"REPEATS 12 TIMES"}
    assert data.comparisons[u"foo"] == [([u"bar"], u"=", u"1")]
    assert data.comparisons[u"bar"] == [([u"foo"], u"NOT >", u"33")]
    assert data.comparisons[u"baz"] == [
        ([u"bar"], u"ISSUBSET", u"'1234'"),
        ([u"quux"], u"NOT LIKE", u"'a_cd'"),
    ]
