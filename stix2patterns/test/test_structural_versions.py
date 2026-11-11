"""
Cross-version checks for the structural pattern view.

Importing and using one STIX version must not change the behaviour of the
other, because both visitors share a common base class.
"""
from stix2patterns.v20.pattern import Pattern as Pattern20
from stix2patterns.v21.pattern import Pattern as Pattern21


def test_versions_are_tagged_independently():
    pattern = u"[foo:bar = 1]"
    assert Pattern20(pattern).structure()[u"stix_version"] == u"2.0"
    assert Pattern21(pattern).structure()[u"stix_version"] == u"2.1"


def test_each_version_uses_its_own_parse_tree():
    # EXISTS only exists in the 2.1 grammar; both visitors must keep working
    # regardless of import/use order (the shared base class must not be
    # mutated by either version module).
    v20_structure = Pattern20(u"[a:b = 1] AND [a:c = 2]").structure()
    v21_exists = Pattern21(u"[EXISTS a:b]").structure()
    v21_structure = Pattern21(u"[a:b = 1] AND [a:c = 2]").structure()

    assert v20_structure[u"stix_version"] == u"2.0"
    assert v21_structure[u"stix_version"] == u"2.1"

    exists_comparison = v21_exists[u"observation"][u"expression"]
    assert exists_comparison[u"operator"] == u"EXISTS"

    # Re-using the 2.0 visitor after touching 2.1 must still work.
    assert Pattern20(u"[a:b = 1]").structure()[u"stix_version"] == u"2.0"


def test_same_pattern_hierarchy_matches_across_versions():
    pattern = u"[a:b=1] AND ([a:c=2] OR [a:d=3])"
    v20 = Pattern20(pattern).structure()[u"observation"]
    v21 = Pattern21(pattern).structure()[u"observation"]

    assert v20[u"operator"] == v21[u"operator"] == u"AND"
    assert v20[u"operands"][1][u"expression"][u"operator"] == u"OR"
    assert v21[u"operands"][1][u"expression"][u"operator"] == u"OR"
