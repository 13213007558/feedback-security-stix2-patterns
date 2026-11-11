"""STIX 2.0 structural pattern visitor."""

from ..structural import StructuralVisitor
from .grammars.STIXPatternVisitor import STIXPatternVisitor


class StructuralPatternVisitor(StructuralVisitor, STIXPatternVisitor):
    """Builds a hierarchical, version-tagged structure from a STIX 2.0
    pattern parse tree.

    The 2.0 grammar has no ``EXISTS`` property test, so that rule can never be
    produced by its parser.  The method is nevertheless overridden (rather
    than removed from the shared base class) so that importing this version
    cannot affect the STIX 2.1 visitor.
    """

    stix_version = u"2.0"

    def visitPropTestExists(self, ctx):
        # Unreachable for STIX 2.0 patterns: the 2.0 grammar does not define
        # a propTestExists rule, so this context can never be produced.
        raise NotImplementedError(
            u"EXISTS property tests are not supported in STIX 2.0 patterns")
