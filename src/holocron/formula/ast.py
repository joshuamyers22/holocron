"""Owned, allowlisted formula abstract syntax tree and parser."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import ClassVar, TypeAlias, cast

from holocron.exceptions import InputValidationError, UnsupportedFeatureError

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SCHEMA_VERSION = "holocron-formula/v2"
MAX_EXPRESSION_LENGTH = 4096
MAX_NAME_LENGTH = 256
MAX_TERMS = 64
MAX_GENERATED_COLUMNS = 256
MAX_POLYNOMIAL_DEGREE = 10
MAX_KNOTS = 32
MAX_LEVELS = 64

_BARE_NAME = re.compile(r"^[^\W\d]\w*$", re.UNICODE)
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _name(value: object, *, role: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_NAME_LENGTH:
        raise InputValidationError(
            f"{role} must be a non-empty string of at most {MAX_NAME_LENGTH} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InputValidationError(f"{role} must not contain control characters")
    return value


def _finite(value: object, *, role: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputValidationError(f"{role} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise InputValidationError(f"{role} must be a finite number")
    return result


def _knots(values: object, *, minimum: int, role: str) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)):
        raise InputValidationError(f"{role} must be a numeric sequence")
    items = cast(list[object] | tuple[object, ...], values)
    result = tuple(_finite(value, role=role) for value in items)
    if not minimum <= len(result) <= MAX_KNOTS:
        raise InputValidationError(
            f"{role} requires between {minimum} and {MAX_KNOTS} knots"
        )
    if any(left >= right for left, right in zip(result, result[1:], strict=False)):
        raise InputValidationError(f"{role} knots must be strictly increasing")
    return result


def quote_name(value: str) -> str:
    """Return a deterministic formula spelling for a validated variable name."""
    name = _name(value, role="variable name")
    if _BARE_NAME.fullmatch(name) and name not in {
        "asis",
        "catg",
        "ia",
        "lsp",
        "pol",
        "rcs",
        "scored",
    }:
        return name
    return f"`{name.replace('`', '``')}`"


@dataclass(frozen=True, slots=True)
class Variable:
    """A named input column reference."""

    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, role="variable name"))

    @property
    def expression(self) -> str:
        """Return the canonical formula spelling."""
        return quote_name(self.name)


@dataclass(frozen=True, slots=True)
class IdentityTerm:
    """An unchanged numeric predictor (the ``asis`` transformation)."""

    variable: Variable
    kind: ClassVar[str] = "identity"

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.variable), Variable):
            raise InputValidationError("term variable must be a Variable")

    @property
    def n_columns(self) -> int:
        return 1

    @property
    def expression(self) -> str:
        return self.variable.expression


@dataclass(frozen=True, slots=True)
class PolynomialTerm:
    """Raw polynomial powers from one through ``degree``."""

    variable: Variable
    degree: int
    kind: ClassVar[str] = "polynomial"

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.variable), Variable):
            raise InputValidationError("term variable must be a Variable")
        raw_degree = cast(object, self.degree)
        if isinstance(raw_degree, bool) or not isinstance(raw_degree, int):
            raise InputValidationError("polynomial degree must be an integer")
        if not 2 <= self.degree <= MAX_POLYNOMIAL_DEGREE:
            raise InputValidationError(
                f"polynomial degree must be between 2 and {MAX_POLYNOMIAL_DEGREE}"
            )

    @property
    def n_columns(self) -> int:
        return self.degree

    @property
    def expression(self) -> str:
        return f"pol({self.variable.expression}, {self.degree})"


@dataclass(frozen=True, slots=True)
class LinearSplineTerm:
    """A linear predictor plus truncated-linear terms at explicit knots."""

    variable: Variable
    knots: tuple[float, ...]
    kind: ClassVar[str] = "linear_spline"

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.variable), Variable):
            raise InputValidationError("term variable must be a Variable")
        object.__setattr__(
            self,
            "knots",
            _knots(self.knots, minimum=1, role="linear spline"),
        )

    @property
    def n_columns(self) -> int:
        return len(self.knots) + 1

    @property
    def expression(self) -> str:
        values = ", ".join(_number_expression(value) for value in self.knots)
        return f"lsp({self.variable.expression}, [{values}])"


@dataclass(frozen=True, slots=True)
class RestrictedCubicSplineTerm:
    """A restricted cubic spline term with explicit knots."""

    variable: Variable
    knots: tuple[float, ...]
    kind: ClassVar[str] = "restricted_cubic_spline"

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.variable), Variable):
            raise InputValidationError("term variable must be a Variable")
        object.__setattr__(
            self,
            "knots",
            _knots(self.knots, minimum=3, role="restricted cubic spline"),
        )

    @property
    def n_columns(self) -> int:
        return len(self.knots) - 1

    @property
    def expression(self) -> str:
        values = ", ".join(_number_expression(value) for value in self.knots)
        return f"rcs({self.variable.expression}, [{values}])"


Level: TypeAlias = str | float


def _levels(
    values: object, *, minimum: int, numeric: bool, role: str
) -> tuple[Level, ...]:
    if not isinstance(values, (list, tuple)):
        raise InputValidationError(f"{role} levels must be a sequence")
    items = cast(list[object] | tuple[object, ...], values)
    if not minimum <= len(items) <= MAX_LEVELS:
        raise InputValidationError(
            f"{role} requires between {minimum} and {MAX_LEVELS} levels"
        )
    result: list[Level] = []
    level_type: type[object] | None = None
    for value in items:
        if isinstance(value, str) and not numeric:
            normalized: Level = _name(value, role=f"{role} level")
            current_type: type[object] = str
        else:
            normalized = _finite(value, role=f"{role} level")
            current_type = float
        if level_type is None:
            level_type = current_type
        elif current_type is not level_type:
            raise InputValidationError(f"{role} levels must have one value type")
        result.append(normalized)
    if len(set(result)) != len(result):
        raise InputValidationError(f"{role} levels must be unique")
    if numeric:
        numeric_result = cast(list[float], result)
        if any(
            left >= right
            for left, right in zip(numeric_result, numeric_result[1:], strict=False)
        ):
            raise InputValidationError(f"{role} levels must be strictly increasing")
    return tuple(result)


def _level_expression(value: Level) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return _number_expression(value)


@dataclass(frozen=True, slots=True)
class CategoricalTerm:
    """An unordered factor with an explicit first/reference level."""

    variable: Variable
    levels: tuple[Level, ...]
    unknown_level: str = "error"
    kind: ClassVar[str] = "categorical"

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.variable), Variable):
            raise InputValidationError("term variable must be a Variable")
        object.__setattr__(
            self,
            "levels",
            _levels(self.levels, minimum=2, numeric=False, role="categorical"),
        )
        if self.unknown_level != "error":
            raise InputValidationError(
                "categorical unknown-level policy must be 'error'"
            )

    @property
    def n_columns(self) -> int:
        return len(self.levels) - 1

    @property
    def expression(self) -> str:
        values = ", ".join(_level_expression(value) for value in self.levels)
        return f"catg({self.variable.expression}, [{values}])"


@dataclass(frozen=True, slots=True)
class OrderedTerm:
    """An ``rms::scored`` ordered factor with explicit numeric levels."""

    variable: Variable
    levels: tuple[float, ...]
    unknown_level: str = "error"
    kind: ClassVar[str] = "ordered"

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.variable), Variable):
            raise InputValidationError("term variable must be a Variable")
        object.__setattr__(
            self,
            "levels",
            cast(
                tuple[float, ...],
                _levels(self.levels, minimum=3, numeric=True, role="ordered"),
            ),
        )
        if self.unknown_level != "error":
            raise InputValidationError("ordered unknown-level policy must be 'error'")

    @property
    def n_columns(self) -> int:
        return len(self.levels) - 1

    @property
    def expression(self) -> str:
        values = ", ".join(_number_expression(value) for value in self.levels)
        return f"scored({self.variable.expression}, [{values}])"


MainEffectTerm: TypeAlias = (
    IdentityTerm
    | PolynomialTerm
    | LinearSplineTerm
    | RestrictedCubicSplineTerm
    | CategoricalTerm
    | OrderedTerm
)


def _nonlinear_flags(term: MainEffectTerm) -> tuple[bool, ...]:
    if isinstance(term, (IdentityTerm, CategoricalTerm)):
        return (False,) * term.n_columns
    return (False,) + (True,) * (term.n_columns - 1)


@dataclass(frozen=True, slots=True)
class RestrictedInteractionTerm:
    """An ``rms`` restricted interaction that excludes doubly nonlinear products."""

    left: MainEffectTerm
    right: MainEffectTerm
    kind: ClassVar[str] = "restricted_interaction"

    def __post_init__(self) -> None:
        if not isinstance(
            cast(object, self.left), _MAIN_EFFECT_TYPES
        ) or not isinstance(cast(object, self.right), _MAIN_EFFECT_TYPES):
            raise InputValidationError(
                "interaction components must be main-effect terms"
            )
        if self.left.variable == self.right.variable:
            raise InputValidationError("interaction variables must be distinct")

    @property
    def n_columns(self) -> int:
        return sum(
            not (left and right)
            for left in _nonlinear_flags(self.left)
            for right in _nonlinear_flags(self.right)
        )

    @property
    def expression(self) -> str:
        return f"ia({self.left.expression}, {self.right.expression})"


FormulaTerm: TypeAlias = MainEffectTerm | RestrictedInteractionTerm


def _number_expression(value: float) -> str:
    return repr(float(value))


def _term_document(term: FormulaTerm) -> dict[str, JsonValue]:
    if isinstance(term, RestrictedInteractionTerm):
        return {
            "kind": term.kind,
            "left": _term_document(term.left),
            "right": _term_document(term.right),
        }
    document: dict[str, JsonValue] = {
        "kind": term.kind,
        "variable": term.variable.name,
    }
    if isinstance(term, PolynomialTerm):
        document["degree"] = term.degree
    if isinstance(term, (LinearSplineTerm, RestrictedCubicSplineTerm)):
        document["knots"] = list(term.knots)
    if isinstance(term, (CategoricalTerm, OrderedTerm)):
        document["levels"] = list(term.levels)
        document["unknown_level"] = term.unknown_level
    return document


@dataclass(frozen=True, slots=True)
class Formula:
    """An immutable, allowlisted formula AST.

    Construct it directly or use :meth:`parse`. The parser implements only the
    documented grammar and never evaluates Python or R source.
    """

    response: Variable | None
    terms: tuple[FormulaTerm, ...]
    include_intercept: bool = True

    def __post_init__(self) -> None:
        raw_response = cast(object, self.response)
        if raw_response is not None and not isinstance(raw_response, Variable):
            raise InputValidationError("formula response must be a Variable or null")
        raw_terms = cast(object, self.terms)
        if not isinstance(raw_terms, tuple):
            raise InputValidationError("formula terms must be a tuple")
        if not self.terms:
            raise InputValidationError("formula requires at least one term")
        if len(self.terms) > MAX_TERMS:
            raise InputValidationError(f"formula exceeds the {MAX_TERMS}-term limit")
        if any(not isinstance(cast(object, term), _TERM_TYPES) for term in self.terms):
            raise InputValidationError("formula contains an unsupported term node")
        if len(set(self.terms)) != len(self.terms):
            raise InputValidationError("formula terms must be unique")
        main_effects = {
            term
            for term in self.terms
            if not isinstance(term, RestrictedInteractionTerm)
        }
        for term in self.terms:
            if isinstance(term, RestrictedInteractionTerm):
                if term.left not in main_effects or term.right not in main_effects:
                    raise InputValidationError(
                        "interaction components must also appear as main effects"
                    )
                reverse = RestrictedInteractionTerm(term.right, term.left)
                if reverse in self.terms and reverse != term:
                    raise InputValidationError(
                        "formula contains a duplicate reversed interaction"
                    )
        column_count = sum(term.n_columns for term in self.terms)
        if column_count > MAX_GENERATED_COLUMNS:
            raise InputValidationError(
                f"formula exceeds the {MAX_GENERATED_COLUMNS}-column limit"
            )
        if not isinstance(cast(object, self.include_intercept), bool):
            raise InputValidationError("include_intercept must be boolean")

    @classmethod
    def parse(cls, expression: str) -> Formula:
        """Parse the restricted formula grammar into owned AST nodes."""
        if not expression.strip():
            raise InputValidationError("formula expression must be non-empty")
        if len(expression) > MAX_EXPRESSION_LENGTH:
            raise InputValidationError(
                f"formula exceeds the {MAX_EXPRESSION_LENGTH}-character limit"
            )
        return _Parser(_tokenize(expression)).parse()

    @property
    def expression(self) -> str:
        """Return a canonical, round-trippable formula expression."""
        left = "" if self.response is None else self.response.expression
        pieces = [term.expression for term in self.terms]
        if not self.include_intercept:
            pieces.insert(0, "0")
        separator = "~" if self.response is None else f"{left} ~"
        return f"{separator} {' + '.join(pieces)}"

    @property
    def predictor_names(self) -> tuple[str, ...]:
        """Return referenced predictor names in first-use order."""
        names: list[str] = []
        for term in self.terms:
            components = (
                (term.left, term.right)
                if isinstance(term, RestrictedInteractionTerm)
                else (term,)
            )
            names.extend(component.variable.name for component in components)
        return tuple(dict.fromkeys(names))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the versioned canonical AST document."""
        return {
            "schema_version": SCHEMA_VERSION,
            "response": None if self.response is None else self.response.name,
            "include_intercept": self.include_intercept,
            "terms": [_term_document(term) for term in self.terms],
        }

    def to_json(self) -> str:
        """Serialize the AST as deterministic JSON."""
        return json.dumps(
            self.to_dict(), allow_nan=False, separators=(",", ":"), sort_keys=True
        )

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical AST document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> Formula:
        """Reconstruct a formula from a strictly versioned AST document."""
        if not isinstance(document, dict):
            raise InputValidationError("formula document must be an object")
        raw = cast(dict[str, object], document)
        required = {"schema_version", "response", "include_intercept", "terms"}
        if set(raw) != required:
            raise InputValidationError("formula document fields differ")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported formula schema version")
        response_value = raw["response"]
        response = (
            None if response_value is None else Variable(cast(str, response_value))
        )
        include_intercept = raw["include_intercept"]
        if not isinstance(include_intercept, bool):
            raise InputValidationError("include_intercept must be boolean")
        raw_terms = raw["terms"]
        if not isinstance(raw_terms, list):
            raise InputValidationError("formula terms must be an array")
        terms = tuple(
            _term_from_document(item) for item in cast(list[object], raw_terms)
        )
        return cls(response=response, terms=terms, include_intercept=include_intercept)

    @classmethod
    def from_json(cls, value: str) -> Formula:
        """Reconstruct a formula from JSON without evaluating source."""
        try:
            document: object = json.loads(value)
        except (json.JSONDecodeError, TypeError) as error:
            raise InputValidationError("invalid formula JSON") from error
        return cls.from_dict(document)


_TERM_TYPES = (
    IdentityTerm,
    PolynomialTerm,
    LinearSplineTerm,
    RestrictedCubicSplineTerm,
    CategoricalTerm,
    OrderedTerm,
    RestrictedInteractionTerm,
)

_MAIN_EFFECT_TYPES = (
    IdentityTerm,
    PolynomialTerm,
    LinearSplineTerm,
    RestrictedCubicSplineTerm,
    CategoricalTerm,
    OrderedTerm,
)


def _term_from_document(value: object) -> FormulaTerm:
    if not isinstance(value, dict):
        raise InputValidationError("each formula term must be an object")
    raw = cast(dict[str, object], value)
    kind = raw.get("kind")
    if kind == "restricted_interaction":
        if set(raw) != {"kind", "left", "right"}:
            raise InputValidationError("formula term document fields differ")
        left = _term_from_document(raw["left"])
        right = _term_from_document(raw["right"])
        if isinstance(left, RestrictedInteractionTerm) or isinstance(
            right, RestrictedInteractionTerm
        ):
            raise InputValidationError("nested interactions are not supported")
        return RestrictedInteractionTerm(left, right)
    expected = {"kind", "variable"}
    if kind == "polynomial":
        expected.add("degree")
    elif kind in {"linear_spline", "restricted_cubic_spline"}:
        expected.add("knots")
    elif kind in {"categorical", "ordered"}:
        expected.update({"levels", "unknown_level"})
    elif kind != "identity":
        raise InputValidationError(f"unknown formula term kind: {kind!r}")
    if set(raw) != expected:
        raise InputValidationError("formula term document fields differ")
    variable = Variable(cast(str, raw["variable"]))
    if kind == "identity":
        return IdentityTerm(variable)
    if kind == "polynomial":
        degree = raw["degree"]
        if isinstance(degree, bool) or not isinstance(degree, int):
            raise InputValidationError("polynomial degree must be an integer")
        return PolynomialTerm(variable, degree)
    if kind == "categorical":
        return CategoricalTerm(
            variable,
            _levels(raw["levels"], minimum=2, numeric=False, role="categorical"),
            cast(str, raw["unknown_level"]),
        )
    if kind == "ordered":
        return OrderedTerm(
            variable,
            cast(
                tuple[float, ...],
                _levels(raw["levels"], minimum=3, numeric=True, role="ordered"),
            ),
            cast(str, raw["unknown_level"]),
        )
    knots = _knots(
        raw["knots"],
        minimum=1 if kind == "linear_spline" else 3,
        role="linear spline" if kind == "linear_spline" else "restricted cubic spline",
    )
    if kind == "linear_spline":
        return LinearSplineTerm(variable, knots)
    return RestrictedCubicSplineTerm(variable, knots)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    position: int


def _tokenize(expression: str) -> tuple[_Token, ...]:
    tokens: list[_Token] = []
    index = 0
    punctuation = {
        "~": "TILDE",
        "+": "PLUS",
        ",": "COMMA",
        "(": "LPAREN",
        ")": "RPAREN",
        "[": "LBRACKET",
        "]": "RBRACKET",
    }
    while index < len(expression):
        character = expression[index]
        if character.isspace():
            index += 1
            continue
        if character in punctuation:
            tokens.append(_Token(punctuation[character], character, index))
            index += 1
            continue
        if character == "-":
            match = _NUMBER.match(expression, index + 1)
            if match is None:
                tokens.append(_Token("MINUS", character, index))
                index += 1
            else:
                tokens.append(_Token("NUMBER", "-" + match.group(), index))
                index = match.end()
            continue
        if character.isdigit() or character == ".":
            match = _NUMBER.match(expression, index)
            if match is None:
                raise InputValidationError(f"invalid number at position {index}")
            tokens.append(_Token("NUMBER", match.group(), index))
            index = match.end()
            continue
        if character == "`":
            start = index
            index += 1
            value: list[str] = []
            while index < len(expression):
                if expression[index] != "`":
                    value.append(expression[index])
                    index += 1
                elif index + 1 < len(expression) and expression[index + 1] == "`":
                    value.append("`")
                    index += 2
                else:
                    index += 1
                    break
            else:
                raise InputValidationError(
                    f"unterminated quoted name at position {start}"
                )
            tokens.append(
                _Token("NAME", _name("".join(value), role="quoted name"), start)
            )
            continue
        if character == '"':
            start = index
            index += 1
            escaped = False
            while index < len(expression):
                current = expression[index]
                if current == '"' and not escaped:
                    index += 1
                    break
                if ord(current) < 32:
                    raise InputValidationError(
                        f"control character in string at position {index}"
                    )
                escaped = current == "\\" and not escaped
                index += 1
            else:
                raise InputValidationError(
                    f"unterminated string literal at position {start}"
                )
            literal = expression[start:index]
            try:
                decoded: object = json.loads(literal)
            except json.JSONDecodeError as error:
                raise InputValidationError(
                    f"invalid string literal at position {start}"
                ) from error
            tokens.append(_Token("STRING", cast(str, decoded), start))
            continue
        if character.isalpha() or character == "_":
            start = index
            index += 1
            while index < len(expression) and (
                expression[index].isalnum() or expression[index] == "_"
            ):
                index += 1
            tokens.append(_Token("NAME", expression[start:index], start))
            continue
        raise UnsupportedFeatureError(
            f"unsupported formula token {character!r} at position {index}"
        )
    tokens.append(_Token("EOF", "", len(expression)))
    return tuple(tokens)


class _Parser:
    def __init__(self, tokens: tuple[_Token, ...]) -> None:
        self._tokens = tokens
        self._index = 0

    @property
    def current(self) -> _Token:
        return self._tokens[self._index]

    def advance(self) -> _Token:
        token = self.current
        self._index += 1
        return token

    def expect(self, kind: str, *, message: str) -> _Token:
        if self.current.kind != kind:
            raise InputValidationError(f"{message} at position {self.current.position}")
        return self.advance()

    def parse(self) -> Formula:
        response: Variable | None = None
        if self.current.kind == "NAME":
            response = Variable(self.advance().value)
        self.expect("TILDE", message="formula requires '~' after the response")
        include_intercept = True
        if self.current.kind == "NUMBER" and self.current.value in {"0", "1"}:
            include_intercept = self.advance().value == "1"
            self.expect("PLUS", message="intercept control must precede formula terms")
        elif self.current.kind == "NUMBER" and self.current.value == "-1":
            self.advance()
            include_intercept = False
            self.expect("PLUS", message="intercept control must precede formula terms")

        terms = [self.parse_term()]
        while self.current.kind == "PLUS":
            self.advance()
            terms.append(self.parse_term())
            if len(terms) > MAX_TERMS:
                raise InputValidationError(
                    f"formula exceeds the {MAX_TERMS}-term limit"
                )
        self.expect("EOF", message="unexpected formula content")
        return Formula(
            response=response,
            terms=tuple(terms),
            include_intercept=include_intercept,
        )

    def parse_term(self) -> FormulaTerm:
        token = self.expect("NAME", message="expected a predictor or transformation")
        variable_or_call = token.value
        if self.current.kind != "LPAREN":
            return IdentityTerm(Variable(variable_or_call))
        if variable_or_call not in {
            "asis",
            "catg",
            "ia",
            "lsp",
            "pol",
            "rcs",
            "scored",
        }:
            raise UnsupportedFeatureError(
                f"unsupported transformation {variable_or_call!r} "
                f"at position {token.position}"
            )
        self.advance()
        if variable_or_call == "ia":
            left = self.parse_component()
            self.expect("COMMA", message="ia requires two component terms")
            right = self.parse_component()
            self.expect("RPAREN", message="ia accepts exactly two component terms")
            return RestrictedInteractionTerm(left, right)
        variable = Variable(
            self.expect("NAME", message="transformation requires a variable").value
        )
        if variable_or_call == "asis":
            self.expect("RPAREN", message="asis accepts only one variable")
            return IdentityTerm(variable)
        self.expect("COMMA", message="transformation parameter is required")
        if variable_or_call == "pol":
            degree_token = self.expect(
                "NUMBER", message="pol degree must be an integer"
            )
            try:
                degree = int(degree_token.value)
            except ValueError as error:
                raise InputValidationError("pol degree must be an integer") from error
            if str(degree) != degree_token.value:
                raise InputValidationError("pol degree must be an integer")
            self.expect("RPAREN", message="pol accepts one degree")
            return PolynomialTerm(variable, degree)
        if variable_or_call == "catg":
            levels = self.parse_level_list()
            self.expect("RPAREN", message="unexpected categorical argument")
            return CategoricalTerm(variable, levels)
        if variable_or_call == "scored":
            levels = self.parse_number_list(role="level", limit=MAX_LEVELS)
            self.expect("RPAREN", message="unexpected ordered argument")
            return OrderedTerm(variable, levels)
        knots = self.parse_number_list(role="knot", limit=MAX_KNOTS)
        self.expect("RPAREN", message="unexpected transformation argument")
        if variable_or_call == "lsp":
            return LinearSplineTerm(variable, knots)
        return RestrictedCubicSplineTerm(variable, knots)

    def parse_component(self) -> MainEffectTerm:
        term = self.parse_term()
        if isinstance(term, RestrictedInteractionTerm):
            raise InputValidationError("nested interactions are not supported")
        return term

    def parse_number_list(self, *, role: str, limit: int) -> tuple[float, ...]:
        self.expect("LBRACKET", message=f"{role}s must use a bracketed numeric list")
        values = [
            _finite(
                float(self.expect("NUMBER", message=f"expected a {role}").value),
                role=role,
            )
        ]
        while self.current.kind == "COMMA":
            self.advance()
            values.append(
                _finite(
                    float(self.expect("NUMBER", message=f"expected a {role}").value),
                    role=role,
                )
            )
            if len(values) > limit:
                raise InputValidationError(
                    f"{role} count exceeds the {limit}-{role} limit"
                )
        self.expect("RBRACKET", message=f"unterminated {role} list")
        return tuple(values)

    def parse_level_list(self) -> tuple[Level, ...]:
        self.expect("LBRACKET", message="levels must use a bracketed literal list")
        kind = self.current.kind
        if kind not in {"NUMBER", "STRING"}:
            raise InputValidationError(
                f"expected a level at position {self.current.position}"
            )

        def take() -> Level:
            token = self.advance()
            if token.kind != kind:
                raise InputValidationError(
                    "categorical levels must have one value type"
                )
            return (
                token.value
                if kind == "STRING"
                else _finite(float(token.value), role="level")
            )

        values = [take()]
        while self.current.kind == "COMMA":
            self.advance()
            values.append(take())
            if len(values) > MAX_LEVELS:
                raise InputValidationError(
                    f"level count exceeds the {MAX_LEVELS}-level limit"
                )
        self.expect("RBRACKET", message="unterminated level list")
        return tuple(values)


__all__ = [
    "Formula",
    "CategoricalTerm",
    "IdentityTerm",
    "LinearSplineTerm",
    "PolynomialTerm",
    "OrderedTerm",
    "RestrictedInteractionTerm",
    "RestrictedCubicSplineTerm",
    "Variable",
]
