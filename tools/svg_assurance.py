"""Structural accessibility checks for Holocron's deterministic SVG output.

This development-time auditor deliberately checks properties that can be
established from the serialized document. It is not a browser, screen-reader,
or WCAG conformance certification tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TypeAlias
from xml.etree import ElementTree as ET

SvgKind: TypeAlias = Literal["plot", "nomogram"]

_SVG = "http://www.w3.org/2000/svg"
_MAX_SVG_BYTES = 8 * 1024 * 1024
_FINGERPRINT = re.compile(
    r"^holocron-(plot-spec|nomogram-geometry)/v1 sha256:[0-9a-f]{64}$"
)
_FORBIDDEN_ELEMENTS = frozenset({"foreignObject", "iframe", "image", "script", "use"})


@dataclass(frozen=True, slots=True)
class SvgAccessibilityFinding:
    """One deterministic SVG assurance failure."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SvgAccessibilityReport:
    """Machine-readable result of auditing one serialized SVG document."""

    kind: SvgKind | None
    title: str | None
    description: str | None
    group_labels: tuple[str, ...]
    layer_ids: tuple[str, ...]
    findings: tuple[SvgAccessibilityFinding, ...]

    @property
    def passed(self) -> bool:
        """Return whether every owned structural check passed."""

        return not self.findings


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _finding(findings: list[SvgAccessibilityFinding], code: str, message: str) -> None:
    findings.append(SvgAccessibilityFinding(code, message))


def _hex_rgb(value: str) -> tuple[int, int, int] | None:
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is None:
        return None
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _relative_luminance(color: str) -> float:
    rgb = _hex_rgb(color)
    if rgb is None:
        raise ValueError("color must use six-digit hexadecimal notation")
    channels = tuple(value / 255.0 for value in rgb)
    linear = tuple(
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str = "#FFFFFF") -> float:
    """Return the WCAG relative-luminance contrast ratio for two hex colors."""

    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _direct_children(root: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in root if child.tag == f"{{{_SVG}}}{name}"]


def _nonempty_text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None or not element.text.strip():
        return None
    return element.text.strip()


def _audit_dimensions(
    root: ET.Element, findings: list[SvgAccessibilityFinding]
) -> None:
    try:
        width = int(root.attrib["width"])
        height = int(root.attrib["height"])
    except (KeyError, ValueError):
        _finding(findings, "dimensions", "width and height must be integer attributes")
        return
    if width <= 0 or height <= 0:
        _finding(findings, "dimensions", "width and height must be positive")
    if root.attrib.get("viewBox") != f"0 0 {width} {height}":
        _finding(findings, "viewbox", "viewBox must match width and height")


def _audit_references(
    root: ET.Element,
    *,
    title: ET.Element | None,
    description: ET.Element | None,
    findings: list[SvgAccessibilityFinding],
) -> None:
    identifiers: list[str] = []
    for element in root.iter():
        identifier = element.attrib.get("id")
        if identifier is not None:
            identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        _finding(findings, "duplicate-id", "SVG element IDs must be unique")

    labelled_by = root.attrib.get("aria-labelledby", "").split()
    expected = [
        element.attrib.get("id", "")
        for element in (title, description)
        if element is not None
    ]
    if not expected or labelled_by != expected or any(not value for value in expected):
        _finding(
            findings,
            "accessible-name",
            "aria-labelledby must reference the direct title and description in order",
        )
    missing = tuple(
        reference for reference in labelled_by if reference not in identifiers
    )
    if missing:
        _finding(
            findings,
            "dangling-reference",
            f"aria-labelledby contains unknown IDs: {', '.join(missing)}",
        )


def _audit_content(
    root: ET.Element, findings: list[SvgAccessibilityFinding]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    group_labels: list[str] = []
    layer_ids: list[str] = []
    for element in root.iter():
        name = _local_name(element.tag)
        if name in _FORBIDDEN_ELEMENTS:
            _finding(findings, "active-content", f"forbidden SVG element: {name}")
        for attribute in element.attrib:
            local_attribute = _local_name(attribute).lower()
            if local_attribute.startswith("on"):
                _finding(
                    findings,
                    "event-handler",
                    f"forbidden event-handler attribute: {local_attribute}",
                )
            if local_attribute == "href":
                _finding(
                    findings,
                    "external-resource",
                    "SVG resource references are not allowed",
                )
        if name == "g" and element.attrib.get("aria-hidden") != "true":
            label = element.attrib.get("aria-label", "").strip()
            if element.attrib.get("role") != "group" or not label:
                _finding(
                    findings,
                    "unlabelled-group",
                    "visible SVG groups must have role=group and a nonempty aria-label",
                )
            else:
                group_labels.append(label)
        if name == "text" and _nonempty_text(element) is None:
            _finding(findings, "empty-text", "rendered text elements must be nonempty")
        layer_id = element.attrib.get("data-layer-id")
        if layer_id is not None:
            layer_ids.append(layer_id)
            if not element.attrib.get("data-role", "").strip():
                _finding(
                    findings,
                    "layer-role",
                    f"plot layer {layer_id!r} has no semantic data-role",
                )
            paints: list[str] = []
            for descendant in element.iter():
                for paint_name in ("fill", "stroke"):
                    paint = descendant.attrib.get(paint_name)
                    if paint is not None and _hex_rgb(paint) is not None:
                        paints.append(paint)
            if not any(contrast_ratio(paint) >= 3.0 for paint in paints):
                _finding(
                    findings,
                    "graphical-contrast",
                    f"plot layer {layer_id!r} has no 3:1 graphical paint against white",
                )
    if len(layer_ids) != len(set(layer_ids)):
        _finding(findings, "duplicate-layer", "data-layer-id values must be unique")
    return tuple(group_labels), tuple(layer_ids)


def _audit_text_contrast(
    root: ET.Element, findings: list[SvgAccessibilityFinding]
) -> None:
    for element in root.iter(f"{{{_SVG}}}text"):
        color = element.attrib.get("fill")
        if color is None or _hex_rgb(color) is None:
            _finding(
                findings,
                "text-color",
                "rendered text must use an explicit six-digit hexadecimal fill",
            )
            continue
        try:
            size = float(element.attrib.get("font-size", "0"))
            weight = int(element.attrib.get("font-weight", "400"))
        except ValueError:
            _finding(findings, "text-style", "text size and weight must be numeric")
            continue
        threshold = 3.0 if size >= 18.0 or (size >= 14.0 and weight >= 700) else 4.5
        if contrast_ratio(color) < threshold:
            text = _nonempty_text(element) or "<empty>"
            _finding(
                findings,
                "text-contrast",
                f"text {text!r} does not meet the {threshold:.1f}:1 contrast threshold",
            )


def audit_svg_accessibility(
    svg: str, *, expected_kind: SvgKind | None = None
) -> SvgAccessibilityReport:
    """Audit the deterministic accessibility contract owned by the SVG renderers."""

    findings: list[SvgAccessibilityFinding] = []
    if not svg.strip():
        return SvgAccessibilityReport(
            None,
            None,
            None,
            (),
            (),
            (SvgAccessibilityFinding("input", "SVG must be a nonempty string"),),
        )
    if len(svg.encode("utf-8")) > _MAX_SVG_BYTES:
        _finding(findings, "input-size", "SVG exceeds the 8 MiB audit limit")
    lowered = svg.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        _finding(
            findings, "document-type", "DOCTYPE and entity declarations are forbidden"
        )
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as error:
        _finding(findings, "xml", f"SVG is not well-formed XML: {error}")
        return SvgAccessibilityReport(None, None, None, (), (), tuple(findings))

    if root.tag != f"{{{_SVG}}}svg":
        _finding(findings, "root", "document root must be an SVG namespace element")
    if root.attrib.get("role") != "img":
        _finding(findings, "role", "SVG root must use role=img")
    if root.attrib.get("focusable") != "false":
        _finding(findings, "focus", "SVG root must set focusable=false")
    _audit_dimensions(root, findings)

    titles = _direct_children(root, "title")
    descriptions = _direct_children(root, "desc")
    title_element = titles[0] if len(titles) == 1 else None
    description_element = descriptions[0] if len(descriptions) == 1 else None
    title = _nonempty_text(title_element)
    description = _nonempty_text(description_element)
    if len(titles) != 1 or title is None:
        _finding(findings, "title", "SVG must contain one nonempty direct title")
    if len(descriptions) != 1 or description is None:
        _finding(
            findings, "description", "SVG must contain one nonempty direct description"
        )
    _audit_references(
        root,
        title=title_element,
        description=description_element,
        findings=findings,
    )

    metadata_elements = _direct_children(root, "metadata")
    metadata = (
        _nonempty_text(metadata_elements[0]) if len(metadata_elements) == 1 else None
    )
    kind: SvgKind | None = None
    match = _FINGERPRINT.fullmatch(metadata or "")
    if match is None:
        _finding(
            findings,
            "metadata",
            "SVG must contain one recognized schema and SHA-256 metadata value",
        )
    else:
        kind = "plot" if match.group(1) == "plot-spec" else "nomogram"
    if expected_kind is not None and kind != expected_kind:
        _finding(
            findings,
            "kind",
            f"expected {expected_kind!r} SVG metadata, found {kind!r}",
        )
    expected_description = (
        None if kind is None else {"plot": "chart", "nomogram": "nomogram"}[kind]
    )
    if root.attrib.get("aria-roledescription") != expected_description:
        _finding(
            findings,
            "role-description",
            f"aria-roledescription must be {expected_description!r}",
        )

    group_labels, layer_ids = _audit_content(root, findings)
    _audit_text_contrast(root, findings)
    return SvgAccessibilityReport(
        kind,
        title,
        description,
        group_labels,
        layer_ids,
        tuple(findings),
    )


def require_accessible_svg(svg: str, *, expected_kind: SvgKind | None = None) -> None:
    """Raise ``ValueError`` when an SVG violates the owned assurance contract."""

    report = audit_svg_accessibility(svg, expected_kind=expected_kind)
    if report.findings:
        details = "; ".join(
            f"{finding.code}: {finding.message}" for finding in report.findings
        )
        raise ValueError(f"SVG accessibility audit failed: {details}")
