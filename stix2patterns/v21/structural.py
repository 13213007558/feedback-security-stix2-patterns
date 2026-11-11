"""STIX 2.1 structural pattern visitor."""

from ..structural import StructuralVisitor
from .grammars.STIXPatternVisitor import STIXPatternVisitor


class StructuralPatternVisitor(StructuralVisitor, STIXPatternVisitor):
    """Builds a hierarchical, version-tagged structure from a STIX 2.1
    pattern parse tree.

    The 2.1 grammar supports the ``EXISTS`` property test, which is handled by
    the base visitor.
    """

    stix_version = u"2.1"
