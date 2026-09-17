"""Build deterministic rms source and namespace inventory artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
REFERENCE_VERSION = "8.2-0"
REFERENCE_COMMIT = "a4e4a305a029090e737562fb4d35bdb705db7d63"
OWNER = "joshuamyers22"

TIER_A = {
    "Design",
    "DesignAssign",
    "Glm",
    "Newlabels",
    "Newlevels",
    "Predict",
    "Xcontrast",
    "asis",
    "catg",
    "contrast",
    "datadist",
    "gTrans",
    "interactions.containing",
    "lrm",
    "lsp",
    "matrx",
    "modelData",
    "ols",
    "pol",
    "predictrms",
    "rcs",
    "scored",
    "specs",
    "strat",
    "summary",
}
TIER_B = {
    "ExProb",
    "Hazard",
    "Mean",
    "Ocens",
    "Ocens2Surv",
    "Ocens2ord",
    "Olinks",
    "Quantile",
    "Survival",
    "adapt_orm",
    "cph",
    "mix_re",
    "npsurv",
    "ordESS",
    "ordParallel",
    "orm",
    "orm.fit",
    "psm",
    "survest",
    "survfit",
}
TIER_C = {
    "bootBCa",
    "bootcov",
    "calibrate",
    "effective.df",
    "fastbw",
    "oos.loglik",
    "pentrace",
    "predab.resample",
    "robcov",
    "val.prob",
    "val.probg",
    "val.surv",
    "validate",
    "vif",
}
PHASE_7 = {
    "Function",
    "annotateAnova",
    "bjplot",
    "bootplot",
    "bplot",
    "confplot",
    "ggplot",
    "hazard.ratio.plot",
    "histdensity",
    "latex",
    "legend.nomabbrev",
    "nomogram",
    "perlcode",
    "plot",
    "plotIntercepts",
    "plotmathAnova",
    "plotp",
    "sascode",
    "survdiffplot",
    "survplot",
    "survplotp",
}


@dataclass(frozen=True, slots=True)
class NamespaceCall:
    name: str
    arguments: tuple[str, ...]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    result: list[str] = []
    for character in line:
        if escaped:
            result.append(character)
            escaped = False
            continue
        if character == "\\":
            result.append(character)
            escaped = True
            continue
        if quote is not None:
            result.append(character)
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            result.append(character)
            quote = character
        elif character == "#":
            break
        else:
            result.append(character)
    return "".join(result)


def namespace_statements(text: str) -> tuple[str, ...]:
    statements: list[str] = []
    buffer: list[str] = []
    depth = 0
    for raw_line in text.splitlines():
        line = strip_comment(raw_line).strip()
        if not line:
            continue
        buffer.append(line)
        depth += line.count("(") - line.count(")")
        if depth == 0:
            statements.append(" ".join(buffer))
            buffer.clear()
    if buffer or depth != 0:
        raise ValueError("unbalanced NAMESPACE statement")
    return tuple(statements)


def split_arguments(value: str) -> tuple[str, ...]:
    arguments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    for character in value:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\":
            current.append(character)
            escaped = True
            continue
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            current.append(character)
            quote = character
        elif character == ",":
            arguments.append("".join(current).strip())
            current.clear()
        else:
            current.append(character)
    if current:
        arguments.append("".join(current).strip())
    return tuple(argument for argument in arguments if argument)


def unquote(value: str) -> str:
    stripped = value.strip()
    if (
        len(stripped) >= 2
        and stripped[0] == stripped[-1]
        and stripped[0]
        in {
            "'",
            '"',
        }
    ):
        return stripped[1:-1]
    return stripped


def parse_namespace(text: str) -> tuple[NamespaceCall, ...]:
    calls: list[NamespaceCall] = []
    for statement in namespace_statements(text):
        opening = statement.find("(")
        if opening < 1 or not statement.endswith(")"):
            raise ValueError(f"unsupported NAMESPACE statement: {statement}")
        calls.append(
            NamespaceCall(
                name=statement[:opening].strip(),
                arguments=tuple(
                    unquote(argument)
                    for argument in split_arguments(statement[opening + 1 : -1])
                ),
            )
        )
    return tuple(calls)


def parse_description(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if line[:1].isspace() and current is not None:
            fields[current] = f"{fields[current]} {line.strip()}"
            continue
        name, separator, value = line.partition(":")
        if not separator:
            continue
        current = name
        fields[name] = value.strip()
    return fields


def capability_tier(name: str) -> tuple[str, str]:
    generic = name.split(".", maxsplit=1)[0]
    if name in TIER_A or generic in TIER_A:
        return "A", "Phase 2-3"
    if name in TIER_B or generic in TIER_B:
        return "B", "Phase 4-5"
    if name in TIER_C or generic in TIER_C:
        return "C", "Phase 6"
    if name in PHASE_7 or generic in PHASE_7:
        return "D", "Phase 7"
    return "D", "Phase 8"


def compatibility_entry(name: str, kind: str) -> dict[str, object]:
    tier, milestone = capability_tier(name)
    implemented = kind == "export" and name in {"ols", "rcs"}
    python_entry = None
    cases: list[str] = []
    tolerance_profile = None
    if name == "rcs" and kind == "export":
        python_entry = "holocron.design.RestrictedCubicSplineSpec"
        cases = ["rcs-explicit"]
        tolerance_profile = "deterministic-transform-v1"
    elif name == "ols" and kind == "export":
        python_entry = "holocron.models.fit_ols"
        cases = ["ols-rcs-explicit"]
        tolerance_profile = "well-conditioned-ols-v1"
    return {
        "id": f"{kind}:{name}",
        "r_symbol": name,
        "kind": kind,
        "python_entry_point": python_entry,
        "tier": tier,
        "milestone": milestone,
        "status": "experimental" if implemented else "deferred",
        "owner": OWNER,
        "oracle_cases": cases,
        "tolerance_profile": tolerance_profile,
        "known_differences": (
            "Initial narrow API; full rms contract remains deferred."
            if implemented
            else "Not yet implemented."
        ),
    }


def build_artifacts(source: Path) -> dict[Path, bytes]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source must be a real directory")
    files = sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix().encode(),
    )
    symlinks = [path for path in source.rglob("*") if path.is_symlink()]
    if symlinks:
        raise ValueError("source snapshot must not contain symbolic links")

    checksum_lines: list[str] = []
    file_entries: list[dict[str, object]] = []
    total_bytes = 0
    for path in files:
        relative = path.relative_to(source).as_posix()
        content = path.read_bytes()
        digest = sha256_bytes(content)
        total_bytes += len(content)
        checksum_lines.append(f"{digest}  {relative}\n")
        file_entries.append({"path": relative, "bytes": len(content), "sha256": digest})
    checksum_bytes = "".join(checksum_lines).encode()

    description = parse_description((source / "DESCRIPTION").read_text())
    if (
        description.get("Package") != "rms"
        or description.get("Version") != REFERENCE_VERSION
    ):
        raise ValueError("source is not the expected rms 8.2-0 snapshot")

    calls = parse_namespace((source / "NAMESPACE").read_text())
    exports = sorted(
        {
            argument
            for call in calls
            if call.name == "export"
            for argument in call.arguments
        }
    )
    s3_methods = sorted(
        {
            f"{call.arguments[0]}.{call.arguments[1]}"
            for call in calls
            if call.name == "S3method" and len(call.arguments) >= 2
        }
    )
    imports = sorted({call.arguments[0] for call in calls if call.name == "import"})
    imports_from = sorted(
        (
            {"package": call.arguments[0], "symbols": list(call.arguments[1:])}
            for call in calls
            if call.name == "importFrom"
        ),
        key=lambda item: str(item["package"]),
    )
    dynamic_libraries = [
        list(call.arguments) for call in calls if call.name == "useDynLib"
    ]
    native_source = (source / "src/init.c").read_text()
    registered_fortran = {
        name: int(parameters)
        for name, parameters in re.findall(
            r'\{"([^"]+)",\s+\(DL_FUNC\).*?,\s+(\d+)\}', native_source
        )
    }
    if not registered_fortran:
        raise ValueError("no registered Fortran routines found in src/init.c")

    inventory = {
        "schema_version": SCHEMA_VERSION,
        "package": "rms",
        "package_version": REFERENCE_VERSION,
        "package_date": description.get("Date"),
        "source_commit": REFERENCE_COMMIT,
        "file_count": len(file_entries),
        "total_bytes": total_bytes,
        "file_manifest_sha256": sha256_bytes(checksum_bytes),
        "namespace_sha256": sha256_bytes((source / "NAMESPACE").read_bytes()),
        "counts": {
            "exports": len(exports),
            "s3_methods": len(s3_methods),
            "import_packages": len(imports),
            "import_from_statements": len(imports_from),
            "registered_fortran": len(registered_fortran),
        },
        "exports": exports,
        "s3_methods": s3_methods,
        "imports": imports,
        "imports_from": imports_from,
        "dynamic_libraries": dynamic_libraries,
        "registered_fortran": registered_fortran,
        "files": file_entries,
    }
    capabilities = [
        *(compatibility_entry(name, "export") for name in exports),
        *(compatibility_entry(name, "s3_method") for name in s3_methods),
    ]
    compatibility = {
        "schema_version": SCHEMA_VERSION,
        "reference": {
            "package": "rms",
            "version": REFERENCE_VERSION,
            "commit": REFERENCE_COMMIT,
            "namespace_sha256": inventory["namespace_sha256"],
        },
        "status_vocabulary": [
            "experimental",
            "implemented",
            "mapped",
            "unsupported",
            "deferred",
        ],
        "default_owner": OWNER,
        "capability_count": len(capabilities),
        "capabilities": capabilities,
    }
    return {
        Path("reference/manifests/rms-8.2-0-files.sha256"): checksum_bytes,
        Path("reference/manifests/rms-8.2-0-inventory.json"): (
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
        ).encode(),
        Path("compatibility/rms-8.2.0.yaml"): (
            json.dumps(compatibility, indent=2, ensure_ascii=False) + "\n"
        ).encode(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    artifacts = build_artifacts(args.source.resolve())
    stale: list[str] = []
    for relative, content in artifacts.items():
        destination = root / relative
        if args.check:
            if not destination.is_file() or destination.read_bytes() != content:
                stale.append(relative.as_posix())
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            print(f"wrote {relative}")
    if stale:
        raise SystemExit(f"stale reference artifacts: {', '.join(stale)}")


if __name__ == "__main__":
    main()
