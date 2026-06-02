"""
Cohort set-algebra (Phase 11 #2) — pure, deterministic, no LLM.

Named segments (saved filter-sets on one cube) combine with set algebra:
  (A & B) - C   →  A intersect B, minus C
compiled into a Cube boolean filter tree:
  &  → {and: [...]}      |  → {or: [...]}      A - B → {and: [A, negate(B)]}

Difference uses De Morgan: negating an AND-group is an OR of negated leaves, and
each leaf operator has a negated counterpart (equals↔notEquals, gt↔lte, ...).
This is the killer retention/funnel primitive and it stays governed: every leaf
member is collected so the caller can validate it against the project catalog
(no arbitrary member injection).

Grammar (precedence: parens > {& , -} left-assoc > | lowest):
    expr   := inter ('|' inter)*
    inter  := atom (('&' | '-') atom)*
    atom   := NAME | '(' expr ')'
NAME is a bare word [A-Za-z0-9_]+ or a "quoted string" (segment names with spaces).
"""
from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r'\s*(?:(?P<op>[&|()\-])|"(?P<q>[^"]*)"|(?P<name>[A-Za-z0-9_]+))')

# Each leaf filter operator's logical negation (for set difference / complement).
_NEGATE_OP = {
    "equals": "notEquals", "notEquals": "equals",
    "contains": "notContains", "notContains": "contains",
    "startsWith": "notStartsWith", "notStartsWith": "startsWith",
    "endsWith": "notEndsWith", "notEndsWith": "endsWith",
    "set": "notSet", "notSet": "set",
    "gt": "lte", "lte": "gt", "gte": "lt", "lt": "gte",
    "inDateRange": "notInDateRange", "notInDateRange": "inDateRange",
    "beforeDate": "afterDate", "afterDate": "beforeDate",
}


class CohortSyntaxError(ValueError):
    """The set-algebra expression couldn't be parsed."""


class UnknownSegment(ValueError):
    """The expression references a segment name that doesn't exist."""


class NonInvertibleFilter(ValueError):
    """A leaf filter operator has no logical negation (so set-difference fails)."""


# ---------- tokenizer ----------

def _tokenize(expr: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(expr):
        if expr[i].isspace():
            i += 1
            continue
        m = _TOKEN.match(expr, i)
        if not m or m.end() == i:
            raise CohortSyntaxError(f"unexpected character at position {i}: {expr[i]!r}")
        if m.group("op"):
            out.append(("op", m.group("op")))
        else:
            out.append(("name", m.group("q") if m.group("q") is not None else m.group("name")))
        i = m.end()
    return out


# ---------- recursive-descent parser → AST ----------
# AST node: ("name", str) | ("and", a, b) | ("or", a, b) | ("diff", a, b)

class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.toks = tokens
        self.pos = 0

    def _peek(self) -> tuple[str, str] | None:
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def _next(self) -> tuple[str, str]:
        t = self._peek()
        if t is None:
            raise CohortSyntaxError("unexpected end of expression")
        self.pos += 1
        return t

    def parse(self) -> Any:
        node = self._expr()
        if self._peek() is not None:
            raise CohortSyntaxError(f"trailing tokens: {self.toks[self.pos:]}")
        return node

    def _expr(self) -> Any:  # union (lowest precedence)
        node = self._inter()
        while self._peek() == ("op", "|"):
            self._next()
            node = ("or", node, self._inter())
        return node

    def _inter(self) -> Any:  # intersection & difference
        node = self._atom()
        while self._peek() in (("op", "&"), ("op", "-")):
            op = self._next()[1]
            rhs = self._atom()
            node = ("and" if op == "&" else "diff", node, rhs)
        return node

    def _atom(self) -> Any:
        t = self._next()
        if t == ("op", "("):
            node = self._expr()
            if self._next() != ("op", ")"):
                raise CohortSyntaxError("expected ')'")
            return node
        if t[0] == "name":
            return ("name", t[1])
        raise CohortSyntaxError(f"unexpected token {t}")


def parse_expression(expr: str) -> Any:
    if not expr or not expr.strip():
        raise CohortSyntaxError("empty expression")
    return _Parser(_tokenize(expr)).parse()


# ---------- compile AST → Cube filter tree ----------

def _leaf_group(filters: list[dict[str, Any]]) -> dict[str, Any]:
    """A segment's filter list is implicitly ANDed."""
    clean = [f for f in filters if isinstance(f, dict) and f.get("member")]
    if not clean:
        return {"and": []}
    if len(clean) == 1:
        return dict(clean[0])
    return {"and": [dict(f) for f in clean]}


def negate(node: dict[str, Any]) -> dict[str, Any]:
    """Logical negation via De Morgan + per-operator inversion."""
    if "and" in node:
        return {"or": [negate(x) for x in node["and"]]}
    if "or" in node:
        return {"and": [negate(x) for x in node["or"]]}
    op = node.get("operator")
    if op not in _NEGATE_OP:
        raise NonInvertibleFilter(
            f"operator {op!r} can't be negated for set-difference; "
            "rewrite the segment with an invertible operator"
        )
    return {"member": node["member"], "operator": _NEGATE_OP[op], "values": node.get("values", [])}


def compile_ast(node: Any, segment_filters: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    kind = node[0]
    if kind == "name":
        name = node[1]
        if name not in segment_filters:
            raise UnknownSegment(f"unknown segment: {name}")
        return _leaf_group(segment_filters[name])
    if kind == "and":
        return {"and": [compile_ast(node[1], segment_filters), compile_ast(node[2], segment_filters)]}
    if kind == "or":
        return {"or": [compile_ast(node[1], segment_filters), compile_ast(node[2], segment_filters)]}
    if kind == "diff":
        return {"and": [compile_ast(node[1], segment_filters),
                        negate(compile_ast(node[2], segment_filters))]}
    raise CohortSyntaxError(f"bad AST node: {node!r}")


def collect_members(node: dict[str, Any]) -> set[str]:
    """All leaf members in a compiled filter tree (for catalog validation)."""
    out: set[str] = set()
    if "and" in node:
        for x in node["and"]:
            out |= collect_members(x)
    elif "or" in node:
        for x in node["or"]:
            out |= collect_members(x)
    elif node.get("member"):
        out.add(node["member"])
    return out


def compile_expression(
    expr: str, segment_filters: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, Any], set[str]]:
    """Parse + compile a set-algebra expression. Returns (cube_filter_tree, members)."""
    tree = compile_ast(parse_expression(expr), segment_filters)
    return tree, collect_members(tree)
