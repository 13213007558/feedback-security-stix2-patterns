"""
Structural inspection of STIX patterns.

Unlike :mod:`stix2patterns.inspector`, which "flattens" a pattern into the set
of comparisons, observation operators and qualifiers it contains, the visitors
in this module produce a hierarchical representation which mirrors the parse
tree.  The nesting of observation-level ``AND``/``OR``/``FOLLOWEDBY``
expressions, the in-bracket comparison expressions, the attribute paths and the
observation expression each ``WITHIN``/``REPEATS``/``START ... STOP`` qualifier
belongs to are all preserved, along with source locations.

The output is made up solely of ``dict`` and ``list`` objects (plus strings,
ints and ``None``), so it can be serialised directly (e.g. to JSON) and handed
to static-analysis code.  It deliberately does not attempt to evaluate a
pattern against any data: this is a structural view, not an event-matching
engine.
"""

from .inspector import INDEX_STAR, _string_literal_to_string

# Key used for source-location metadata on every node.
POSITION = u"position"

# Node "type" values.
NODE_PATTERN = u"pattern"
NODE_COMPARISON = u"comparison"
NODE_COMPARISON_OPERATOR = u"comparison_operator"
NODE_OBSERVATION = u"observation"
NODE_OBSERVATION_OPERATOR = u"observation_operator"
NODE_QUALIFIER = u"qualifier"

# Observation-level boolean/sequence operators.
OP_AND = u"AND"
OP_OR = u"OR"
OP_FOLLOWEDBY = u"FOLLOWEDBY"

# Qualifier types.
QUAL_WITHIN = u"WITHIN"
QUAL_REPEATS = u"REPEATS"
QUAL_START_STOP = u"START_STOP"


def _position(ctx):
    """Build a source-location dict for an ANTLR parser-rule context.

    The offsets are zero-based character offsets into the original pattern
    string and the line/column pair is one-based line / zero-based column,
    matching the ANTLR token conventions.  The caller can use them to point a
    reported problem back at the exact expression text.
    """
    start = ctx.start
    stop = ctx.stop or start

    return {
        u"line": start.line,
        u"column": start.column,
        u"start": start.start,
        u"end": stop.stop + 1,
    }


def _node(node_type, ctx, **fields):
    """Create a node dict, attaching its source location."""
    node = {u"type": node_type}
    node.update(fields)
    node[POSITION] = _position(ctx)
    return node


def _negated(ctx):
    return ctx.NOT() is not None


class StructuralVisitor(object):
    """Common structural-visitor logic for the STIX 2.0 and 2.1 grammars.

    Subclasses only need to bind the version-specific generated parser and
    visitor base class (the parse-tree structure and method names are
    otherwise identical between the two grammar versions).
    """

    #: The STIX version string stamped onto the produced structure.
    stix_version = None

    def visit(self, tree):
        return tree.accept(self)

    # -- Entry point ---------------------------------------------------------

    def visitPattern(self, ctx):
        observation = ctx.observationExpressions().accept(self)
        return _node(
            NODE_PATTERN, ctx,
            stix_version=self.stix_version,
            observation=observation,
        )

    # -- Observation expressions --------------------------------------------

    def visitObservationExpressions(self, ctx):
        # Left-recursive rule: a FOLLOWEDBY node wraps the two operands;
        # otherwise the node is just the single (OR-level) expression.
        if ctx.FOLLOWEDBY():
            children = ctx.observationExpressions()
            operands = [child.accept(self) for child in children]
            return _node(
                NODE_OBSERVATION_OPERATOR, ctx,
                operator=OP_FOLLOWEDBY,
                operands=operands,
            )

        return ctx.observationExpressionOr().accept(self)

    def visitObservationExpressionOr(self, ctx):
        or_children = ctx.observationExpressionOr()
        if ctx.OR():
            operands = [or_children[0].accept(self),
                        or_children[1].accept(self)]
            return _node(
                NODE_OBSERVATION_OPERATOR, ctx,
                operator=OP_OR,
                operands=operands,
            )

        return ctx.observationExpressionAnd().accept(self)

    def visitObservationExpressionAnd(self, ctx):
        and_children = ctx.observationExpressionAnd()
        if ctx.AND():
            operands = [and_children[0].accept(self),
                        and_children[1].accept(self)]
            return _node(
                NODE_OBSERVATION_OPERATOR, ctx,
                operator=OP_AND,
                operands=operands,
            )

        return ctx.observationExpression().accept(self)

    def visitObservationExpressionSimple(self, ctx):
        expression = ctx.comparisonExpression().accept(self)
        object_type = _first_comparison(expression)[u"object_path"][u"object_type"]
        return _node(
            NODE_OBSERVATION, ctx,
            object_type=object_type,
            expression=expression,
            qualifiers=[],
        )

    def visitObservationExpressionCompound(self, ctx):
        expression = ctx.observationExpressions().accept(self)
        return _node(
            NODE_OBSERVATION, ctx,
            object_type=None,
            expression=expression,
            qualifiers=[],
        )

    def visitObservationExpressionWithin(self, ctx):
        return self._qualify(ctx, self._within_qualifier(ctx.withinQualifier()))

    def visitObservationExpressionStartStop(self, ctx):
        return self._qualify(
            ctx, self._start_stop_qualifier(ctx.startStopQualifier()))

    def visitObservationExpressionRepeated(self, ctx):
        return self._qualify(
            ctx, self._repeated_qualifier(ctx.repeatedQualifier()))

    def _qualify(self, ctx, qualifier):
        # Recursion builds the inner (already possibly qualified) observation
        # expression; the qualifier is attached to that expression so the
        # ownership relationship visible in the parse tree is retained.
        observation = ctx.observationExpression().accept(self)
        observation[u"qualifiers"].append(qualifier)
        return _node(
            NODE_OBSERVATION, ctx,
            object_type=observation.get(u"object_type"),
            expression=observation[u"expression"],
            qualifiers=observation[u"qualifiers"],
        )

    # -- Qualifiers ----------------------------------------------------------

    def _within_qualifier(self, ctx):
        number = ctx.IntPosLiteral() or ctx.FloatPosLiteral()
        return _node(
            NODE_QUALIFIER, ctx,
            qualifier=QUAL_WITHIN,
            value=number.getText(),
        )

    def _repeated_qualifier(self, ctx):
        return _node(
            NODE_QUALIFIER, ctx,
            qualifier=QUAL_REPEATS,
            value=ctx.IntPosLiteral().getText(),
        )

    def _start_stop_qualifier(self, ctx):
        return _node(
            NODE_QUALIFIER, ctx,
            qualifier=QUAL_START_STOP,
            start_time=ctx.TimestampLiteral(0).getText(),
            stop_time=ctx.TimestampLiteral(1).getText(),
        )

    # -- In-bracket comparison expressions ----------------------------------

    def visitComparisonExpression(self, ctx):
        or_children = ctx.comparisonExpression()
        if ctx.OR():
            operands = [child.accept(self) for child in or_children]
            return _node(
                NODE_COMPARISON_OPERATOR, ctx,
                operator=OP_OR,
                operands=operands,
            )

        return ctx.comparisonExpressionAnd().accept(self)

    def visitComparisonExpressionAnd(self, ctx):
        and_children = ctx.comparisonExpressionAnd()
        if ctx.AND():
            operands = [child.accept(self) for child in and_children]
            return _node(
                NODE_COMPARISON_OPERATOR, ctx,
                operator=OP_AND,
                operands=operands,
            )

        return ctx.propTest().accept(self)

    def visitPropTestParen(self, ctx):
        # Parentheses alter the parse tree (and thus precedence), so the
        # grouping is represented explicitly rather than collapsed away.
        return _node(
            NODE_COMPARISON_OPERATOR, ctx,
            operator=None,
            operands=[ctx.comparisonExpression().accept(self)],
            grouped=True,
        )

    def visitPropTestEqual(self, ctx):
        operator = u"!=" if ctx.NEQ() else u"="
        return self._comparison(
            ctx, operator, ctx.primitiveLiteral().getText(), negated=_negated(ctx))

    def visitPropTestOrder(self, ctx):
        operator_token = ctx.GT() or ctx.LT() or ctx.GE() or ctx.LE()
        return self._comparison(
            ctx, operator_token.getText(), ctx.orderableLiteral().getText(),
            negated=_negated(ctx))

    def visitPropTestSet(self, ctx):
        return self._comparison(
            ctx, u"IN", ctx.setLiteral().getText(), negated=_negated(ctx))

    def visitPropTestLike(self, ctx):
        return self._comparison(
            ctx, u"LIKE", ctx.StringLiteral().getText(), negated=_negated(ctx))

    def visitPropTestRegex(self, ctx):
        return self._comparison(
            ctx, u"MATCHES", ctx.StringLiteral().getText(),
            negated=_negated(ctx))

    def visitPropTestIsSubset(self, ctx):
        return self._comparison(
            ctx, u"ISSUBSET", ctx.StringLiteral().getText(),
            negated=_negated(ctx))

    def visitPropTestIsSuperset(self, ctx):
        return self._comparison(
            ctx, u"ISSUPERSET", ctx.StringLiteral().getText(),
            negated=_negated(ctx))

    def visitPropTestExists(self, ctx):
        # Only present in the STIX 2.1 grammar; the 2.0 subclass does not bind
        # this method.  EXISTS is a prefix operator, so it carries no value.
        object_path = ctx.objectPath().accept(self)
        return _node(
            NODE_COMPARISON, ctx,
            negated=_negated(ctx),
            operator=u"EXISTS",
            object_path=object_path,
            value=None,
        )

    def _comparison(self, ctx, operator, value, negated):
        object_path = ctx.objectPath().accept(self)
        return _node(
            NODE_COMPARISON, ctx,
            negated=negated,
            operator=operator,
            object_path=object_path,
            value=value,
        )

    # -- Object paths --------------------------------------------------------

    def visitObjectPath(self, ctx):
        path = [ctx.firstPathComponent().accept(self)]

        component = ctx.objectPathComponent()
        if component is not None:
            path.extend(component.accept(self))

        return {
            u"object_type": ctx.objectType().getText(),
            u"path": path,
            u"position": _position(ctx),
        }

    def visitFirstPathComponent(self, ctx):
        if ctx.StringLiteral():
            return _string_literal_to_string(ctx.StringLiteral())
        return ctx.getText()

    def visitKeyPathStep(self, ctx):
        if ctx.IdentifierWithoutHyphen():
            return ctx.IdentifierWithoutHyphen().getText()
        return _string_literal_to_string(ctx.StringLiteral())

    def visitIndexPathStep(self, ctx):
        if ctx.ASTERISK():
            return INDEX_STAR
        if ctx.IntNegLiteral():
            return int(ctx.IntNegLiteral().getText())
        return int(ctx.IntPosLiteral().getText())

    def visitPathStep(self, ctx):
        # Left-recursive rule: each nested PathStep wraps another component,
        # so recurse and flatten into a single ordered list of steps.
        steps = []
        for component in ctx.objectPathComponent():
            result = component.accept(self)
            if isinstance(result, list):
                steps.extend(result)
            else:
                steps.append(result)
        return steps

    # -- Helpers -------------------------------------------------------------


def _first_comparison(node):
    """Return the leftmost comparison leaf of a (possibly nested) comparison
    expression node."""
    if node[u"type"] == NODE_COMPARISON:
        return node
    return _first_comparison(node[u"operands"][0])
