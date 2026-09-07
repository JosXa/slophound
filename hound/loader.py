"""Load and validate the TOML rule files in `rules/`.

The file name is the category (`rules/verb.toml` holds `verb.*` rules) and the
category decides which detection layer executes the rule. Validation is strict
on purpose: a malformed rule is a tool failure (exit 2), never a silent skip.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from .model import CATEGORIES, DOC_CATEGORIES, REGEX_CATEGORIES, SEVERITIES, SEVERITY_ALIASES, SPACY_CATEGORIES, Rule

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


class RuleError(Exception):
    pass


def load_rules(rules_dir: Path = RULES_DIR) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for category in CATEGORIES:
        path = rules_dir / f"{category}.toml"
        if not path.exists():
            continue
        with path.open("rb") as fh:
            try:
                data = tomllib.load(fh)
            except tomllib.TOMLDecodeError as exc:
                raise RuleError(f"{path}: {exc}") from exc
        for raw in data.get("rule", []):
            rule = _build_rule(raw, category, path)
            if rule.id in seen:
                raise RuleError(f"{path}: duplicate rule id {rule.id}")
            seen.add(rule.id)
            rules.append(rule)
    if not rules:
        raise RuleError(f"no rules found in {rules_dir}")
    return rules


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    raise RuleError("expected a string or list of strings")


def _build_rule(raw: dict, category: str, path: Path) -> Rule:
    rid = raw.get("id")
    if not isinstance(rid, str) or not rid.startswith(category + "."):
        raise RuleError(f"{path}: rule id {rid!r} must start with '{category}.'")
    where = f"{path} [{rid}]"
    if not re.fullmatch(r"[a-z]+\.[a-z0-9][a-z0-9-]*", rid):
        raise RuleError(f"{where}: id must be lowercase kind.slug")

    severity = raw.get("severity")
    severity = SEVERITY_ALIASES.get(severity, severity)
    if severity not in SEVERITIES:
        raise RuleError(f"{where}: severity must be one of {SEVERITIES}")

    message = raw.get("message")
    if not isinstance(message, str) or not message.strip():
        raise RuleError(f"{where}: message is required")

    try:
        example = _as_list(raw.get("example", []))
        acceptable = _as_list(raw.get("acceptable", []))
        most_common_in = _as_list(raw.get("most_common_in", []))
    except RuleError as exc:
        raise RuleError(f"{where}: {exc}") from exc
    if not example:
        raise RuleError(f"{where}: at least one example is required")
    if not acceptable:
        raise RuleError(f"{where}: at least one acceptable sentence is required")

    rule = Rule(
        id=rid,
        category=category,
        severity=severity,
        message=message.strip(),
        example=example,
        acceptable=acceptable,
        source_file=path,
        most_common_in=most_common_in,
        headings=bool(raw.get("headings", category == "phrase")),
    )

    if category in REGEX_CATEGORIES:
        pattern = raw.get("pattern")
        if not isinstance(pattern, str):
            raise RuleError(f"{where}: pattern (regex string) is required")
        try:
            re.compile(pattern, re.I | re.M)
        except re.error as exc:
            raise RuleError(f"{where}: invalid regex: {exc}") from exc
        rule.pattern = pattern
        unless = raw.get("unless")
        if unless is not None:
            if not isinstance(unless, str):
                raise RuleError(f"{where}: unless must be a regex string")
            try:
                re.compile(unless, re.I)
            except re.error as exc:
                raise RuleError(f"{where}: invalid unless regex: {exc}") from exc
            rule.unless = unless
    elif category in SPACY_CATEGORIES:
        dependency = raw.get("dependency")
        # One pattern is a list of node tables; a rule may also give several
        # alternative patterns as a list of such lists. Normalise to the latter.
        if isinstance(dependency, list) and dependency and all(isinstance(n, dict) for n in dependency):
            dependency = [dependency]
        if (
            not isinstance(dependency, list)
            or not dependency
            or not all(isinstance(p, list) and p and all(isinstance(n, dict) for n in p) for p in dependency)
        ):
            raise RuleError(f"{where}: dependency must be a non-empty list of node tables (or a list of such lists)")
        for pattern in dependency:
            for node in pattern:
                if "RIGHT_ID" not in node or "RIGHT_ATTRS" not in node:
                    raise RuleError(f"{where}: every dependency node needs RIGHT_ID and RIGHT_ATTRS")
        rule.dependency = dependency
        unless = raw.get("unless")
        if unless is not None:
            if not isinstance(unless, str):
                raise RuleError(f"{where}: unless must be a regex string")
            rule.unless = unless
    elif category in DOC_CATEGORIES:
        metric = raw.get("metric")
        if not isinstance(metric, str):
            raise RuleError(f"{where}: metric name is required")
        threshold = raw.get("threshold")
        if not isinstance(threshold, (int, float)):
            raise RuleError(f"{where}: numeric threshold is required")
        rule.metric = metric
        rule.threshold = float(threshold)
        rule.min_sentences = int(raw.get("min_sentences", 0))
        rule.min_paragraphs = int(raw.get("min_paragraphs", 0))
    return rule
