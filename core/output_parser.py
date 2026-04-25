# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Output Intelligence — Production Grade
Detects and structures: JSON, YAML, TOML, XML, tables, CSVs, logs, diffs,
stack traces, trees, key-value pairs, and lists. Includes smart summarization.
"""

import re
import json
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum


class OutputType(Enum):
    """Detected output type."""
    PLAIN = "plain"
    TABLE = "table"
    JSON_DATA = "json"
    YAML_DATA = "yaml"
    TOML_DATA = "toml"
    XML_DATA = "xml"
    LOG = "log"
    STACK_TRACE = "stacktrace"
    KEY_VALUE = "key_value"
    LIST = "list"
    TREE = "tree"
    CSV = "csv"
    DIFF = "diff"
    INI = "ini"
    EMPTY = "empty"
    BINARY = "binary"


@dataclass
class ParsedOutput:
    """Result of output parsing."""
    raw: str
    output_type: OutputType
    structured_data: Optional[object] = None
    line_count: int = 0
    summary: str = ""
    language_hint: str = ""       # for syntax highlighting
    has_errors: bool = False
    error_count: int = 0
    warning_count: int = 0
    truncated: bool = False


class OutputParser:
    """
    Production-grade output parser.

    Features:
    - 16 output type detectors
    - YAML/TOML/XML structured parsing
    - Diff/patch detection with add/remove counting
    - Log severity analysis with error/warning counts
    - Stack trace extraction (Python, Node, Java, Rust, Go)
    - INI/config file detection
    - Binary output detection
    - Smart summarization
    - Language hints for syntax highlighting
    """

    MAX_PARSE_BYTES = 1024 * 1024  # 1MB limit

    # ── Log patterns ──────────────────────────────────────
    LOG_PATTERN = re.compile(
        r"^\[?"
        r"(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL|TRACE)"
        r"\]?\s*[:\-\|]?\s*",
        re.IGNORECASE | re.MULTILINE,
    )

    TIMESTAMP_LOG = re.compile(
        r"^\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2}",
        re.MULTILINE,
    )

    # ── Stack trace patterns ──────────────────────────────
    PYTHON_TRACE = re.compile(r"Traceback \(most recent call last\)")
    NODE_TRACE = re.compile(r"^\s+at\s+.+\(.+:\d+:\d+\)", re.MULTILINE)
    JAVA_TRACE = re.compile(r"^\s+at\s+[\w.]+\([\w.]+:\d+\)", re.MULTILINE)
    RUST_TRACE = re.compile(r"thread '.*' panicked at", re.MULTILINE)
    GO_TRACE = re.compile(r"^goroutine \d+ \[", re.MULTILINE)
    GENERIC_ERROR = re.compile(
        r"^(Error|Exception|Fatal|FATAL|Caused by|panic:)[\s:]",
        re.MULTILINE,
    )

    # ── Table patterns ────────────────────────────────────
    TABLE_SEPARATOR = re.compile(r"^[\-\+\=\|]+$", re.MULTILINE)
    COLUMN_ALIGNMENT = re.compile(r"\s{2,}")

    # ── Tree patterns ─────────────────────────────────────
    TREE_PATTERN = re.compile(r"^[\s│├└─┬┤]*[├└│]", re.MULTILINE)

    # ── Diff patterns ─────────────────────────────────────
    DIFF_HEADER = re.compile(r"^(---|\+\+\+|@@|diff\s+--git)\s", re.MULTILINE)
    DIFF_LINE = re.compile(r"^[+\-]\s", re.MULTILINE)

    # ── YAML patterns ─────────────────────────────────────
    YAML_PATTERN = re.compile(r"^[\w\-]+:\s*.+$", re.MULTILINE)
    YAML_LIST = re.compile(r"^\s*-\s+\w+", re.MULTILINE)

    # ── XML patterns ──────────────────────────────────────
    XML_PATTERN = re.compile(r"^<\?xml\s|^<\w+[\s>]", re.MULTILINE)

    # ── INI patterns ──────────────────────────────────────
    INI_SECTION = re.compile(r"^\[[\w\s\.\-]+\]\s*$", re.MULTILINE)
    INI_KV = re.compile(r"^\w[\w\.\-]*\s*=\s*.+$", re.MULTILINE)

    def parse(self, output: str) -> ParsedOutput:
        """Parse raw output and detect its type."""
        if not output or not output.strip():
            return ParsedOutput(raw=output, output_type=OutputType.EMPTY, line_count=0)

        # Limit parsing for very large outputs
        truncated = len(output) > self.MAX_PARSE_BYTES
        if truncated:
            output = output[:self.MAX_PARSE_BYTES]

        # Binary detection
        if self._is_binary(output):
            return ParsedOutput(
                raw=output, output_type=OutputType.BINARY,
                summary="Binary output detected",
            )

        lines = output.strip().split("\n")
        line_count = len(lines)

        # Try each detector in order of specificity
        detectors = [
            self._detect_json,
            self._detect_xml,
            self._detect_diff,
            self._detect_stack_trace,
            self._detect_yaml,
            self._detect_toml,
            self._detect_ini,
            self._detect_csv,
            self._detect_table,
            self._detect_log,
            self._detect_tree,
            self._detect_key_value,
            self._detect_list,
        ]

        for detector in detectors:
            result = detector(output, lines)
            if result:
                result.line_count = line_count
                result.truncated = truncated
                return result

        return ParsedOutput(
            raw=output,
            output_type=OutputType.PLAIN,
            line_count=line_count,
            summary=f"{line_count} lines of text",
            truncated=truncated,
        )

    def summarize(self, parsed: ParsedOutput, max_lines: int = 5) -> str:
        """Generate a human-readable summary of parsed output."""
        parts = [f"[{parsed.output_type.value.upper()}]"]

        if parsed.summary:
            parts.append(parsed.summary)

        if parsed.has_errors:
            parts.append(f"⚠ {parsed.error_count} errors, {parsed.warning_count} warnings")

        if parsed.line_count > max_lines:
            parts.append(f"({parsed.line_count} lines)")

        if parsed.truncated:
            parts.append("[TRUNCATED]")

        return " — ".join(parts)

    # ═══════════════════════════════════════════════════════
    # Detectors
    # ═══════════════════════════════════════════════════════

    def _detect_json(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect JSON output."""
        stripped = output.strip()
        if not (stripped.startswith(("{", "[")) and stripped.endswith(("}", "]"))):
            return None

        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                summary = f"JSON object with {len(data)} keys: {', '.join(list(data.keys())[:5])}"
            elif isinstance(data, list):
                summary = f"JSON array with {len(data)} items"
            else:
                summary = "JSON value"

            return ParsedOutput(
                raw=output,
                output_type=OutputType.JSON_DATA,
                structured_data=data,
                summary=summary,
                language_hint="json",
            )
        except json.JSONDecodeError:
            return None

    def _detect_xml(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect XML output."""
        stripped = output.strip()
        if not self.XML_PATTERN.match(stripped):
            return None

        # Count tags
        tag_count = len(re.findall(r"<[\w\-]+[\s>]", stripped))
        if tag_count < 2:
            return None

        # Extract root element
        root_match = re.match(r"<(\w+)", stripped.lstrip("<?xml ").lstrip())
        root = root_match.group(1) if root_match else "unknown"

        return ParsedOutput(
            raw=output,
            output_type=OutputType.XML_DATA,
            structured_data={"root": root, "tag_count": tag_count},
            summary=f"XML document, root: <{root}>, {tag_count} elements",
            language_hint="xml",
        )

    def _detect_diff(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect diff/patch output."""
        header_count = len(self.DIFF_HEADER.findall(output))
        diff_lines = len(self.DIFF_LINE.findall(output))

        if header_count >= 1 and diff_lines >= 2:
            additions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
            deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))

            return ParsedOutput(
                raw=output,
                output_type=OutputType.DIFF,
                structured_data={
                    "additions": additions,
                    "deletions": deletions,
                    "files_changed": header_count // 3 or 1,
                },
                summary=f"Diff: +{additions} -{deletions} in ~{header_count // 3 or 1} file(s)",
                language_hint="diff",
            )
        return None

    def _detect_stack_trace(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect error stack traces (Python, Node, Java, Rust, Go)."""
        trace_type = ""
        if self.PYTHON_TRACE.search(output):
            trace_type = "Python"
        elif self.NODE_TRACE.search(output):
            trace_type = "Node.js"
        elif self.JAVA_TRACE.search(output):
            trace_type = "Java"
        elif self.RUST_TRACE.search(output):
            trace_type = "Rust"
        elif self.GO_TRACE.search(output):
            trace_type = "Go"
        elif self.GENERIC_ERROR.search(output) and len(lines) > 2:
            trace_type = "Generic"

        if not trace_type:
            return None

        # Extract the error message
        error_line = ""
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith(" ") and not line.startswith("at "):
                error_line = line
                break

        return ParsedOutput(
            raw=output,
            output_type=OutputType.STACK_TRACE,
            structured_data={"error": error_line, "trace_type": trace_type, "trace_lines": len(lines)},
            summary=f"{trace_type} error: {error_line[:80]}",
            language_hint="python" if trace_type == "Python" else "",
            has_errors=True,
            error_count=1,
        )

    def _detect_yaml(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect YAML output."""
        yaml_lines = sum(1 for l in lines if self.YAML_PATTERN.match(l.strip()))
        yaml_list_lines = sum(1 for l in lines if self.YAML_LIST.match(l))

        if (yaml_lines + yaml_list_lines) >= len(lines) * 0.5 and yaml_lines >= 3:
            # Don't confuse with key-value
            if ":" in lines[0] and not lines[0].strip().startswith("["):
                return ParsedOutput(
                    raw=output,
                    output_type=OutputType.YAML_DATA,
                    structured_data={"key_count": yaml_lines},
                    summary=f"YAML with {yaml_lines} keys",
                    language_hint="yaml",
                )
        return None

    def _detect_toml(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect TOML output."""
        section_count = len(self.INI_SECTION.findall(output))
        # TOML uses dotted keys
        dotted_keys = sum(1 for l in lines if re.match(r"^\w+\.\w+\s*=", l.strip()))

        if section_count >= 1 and dotted_keys >= 1:
            return ParsedOutput(
                raw=output,
                output_type=OutputType.TOML_DATA,
                structured_data={"sections": section_count},
                summary=f"TOML with {section_count} sections",
                language_hint="toml",
            )
        return None

    def _detect_ini(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect INI/config file output."""
        section_count = len(self.INI_SECTION.findall(output))
        kv_count = len(self.INI_KV.findall(output))

        if section_count >= 2 and kv_count >= 3:
            return ParsedOutput(
                raw=output,
                output_type=OutputType.INI,
                structured_data={"sections": section_count, "keys": kv_count},
                summary=f"INI config: {section_count} sections, {kv_count} keys",
                language_hint="ini",
            )
        return None

    def _detect_csv(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect CSV-like output."""
        if len(lines) < 2:
            return None

        comma_counts = [line.count(",") for line in lines[:10] if line.strip()]
        if not comma_counts or comma_counts[0] == 0:
            return None

        if len(set(comma_counts)) <= 2 and comma_counts[0] >= 2:
            headers = [h.strip() for h in lines[0].split(",")]
            return ParsedOutput(
                raw=output,
                output_type=OutputType.CSV,
                structured_data={"headers": headers, "row_count": len(lines) - 1},
                summary=f"CSV: {len(headers)} columns, {len(lines) - 1} rows",
                language_hint="csv",
            )
        return None

    def _detect_table(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect tabular output."""
        if len(lines) < 3:
            return None

        has_separator = bool(self.TABLE_SEPARATOR.search(output))

        if not has_separator:
            space_positions = []
            for line in lines[:5]:
                positions = [m.start() for m in self.COLUMN_ALIGNMENT.finditer(line)]
                if positions:
                    space_positions.append(tuple(positions))

            if len(space_positions) >= 2:
                first = space_positions[0]
                consistent = sum(1 for p in space_positions if len(p) == len(first)) >= len(space_positions) * 0.6
                if not consistent:
                    return None
            else:
                return None

        return ParsedOutput(
            raw=output,
            output_type=OutputType.TABLE,
            structured_data={"row_count": len(lines)},
            summary=f"Table with ~{len(lines)} rows",
        )

    def _detect_log(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect log output with severity analysis."""
        log_lines = sum(1 for line in lines if self.LOG_PATTERN.match(line))
        ts_lines = sum(1 for line in lines if self.TIMESTAMP_LOG.match(line))

        if log_lines >= len(lines) * 0.3 or ts_lines >= len(lines) * 0.3:
            errors = 0
            warnings = 0
            for line in lines:
                lower = line.lower()
                if "error" in lower or "fatal" in lower or "critical" in lower:
                    errors += 1
                elif "warn" in lower:
                    warnings += 1

            return ParsedOutput(
                raw=output,
                output_type=OutputType.LOG,
                structured_data={"errors": errors, "warnings": warnings, "total": len(lines)},
                summary=f"Log: {errors} errors, {warnings} warnings, {len(lines)} total",
                has_errors=errors > 0,
                error_count=errors,
                warning_count=warnings,
            )
        return None

    def _detect_tree(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect tree-structure output."""
        tree_lines = sum(1 for line in lines if self.TREE_PATTERN.match(line))
        if tree_lines >= len(lines) * 0.4:
            return ParsedOutput(
                raw=output,
                output_type=OutputType.TREE,
                structured_data={"nodes": len(lines)},
                summary=f"Tree structure with {len(lines)} nodes",
            )
        return None

    def _detect_key_value(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect key-value pair output."""
        kv_pattern = re.compile(r"^[\w\s\-\.]+\s*[:=]\s*.+$")
        kv_lines = sum(1 for line in lines if kv_pattern.match(line.strip()))

        if kv_lines >= len(lines) * 0.5 and kv_lines >= 3:
            data = {}
            for line in lines:
                for sep in [":", "="]:
                    if sep in line:
                        key, _, val = line.partition(sep)
                        data[key.strip()] = val.strip()
                        break

            return ParsedOutput(
                raw=output,
                output_type=OutputType.KEY_VALUE,
                structured_data=data,
                summary=f"{len(data)} key-value pairs",
            )
        return None

    def _detect_list(self, output: str, lines: list[str]) -> Optional[ParsedOutput]:
        """Detect bulleted/numbered list output."""
        list_pattern = re.compile(r"^\s*[\-\*\•\d+\.]\s+.+$")
        list_lines = sum(1 for line in lines if list_pattern.match(line))

        if list_lines >= len(lines) * 0.5 and list_lines >= 3:
            return ParsedOutput(
                raw=output,
                output_type=OutputType.LIST,
                structured_data={"item_count": list_lines},
                summary=f"List with {list_lines} items",
            )
        return None

    def _is_binary(self, output: str) -> bool:
        """Check if output contains binary data."""
        try:
            null_count = output.count("\x00")
            if null_count > 0:
                return True
            # High ratio of non-printable characters
            non_printable = sum(1 for c in output[:1000]
                                if ord(c) < 32 and c not in "\n\r\t")
            return non_printable > len(output[:1000]) * 0.1
        except Exception:
            return False
