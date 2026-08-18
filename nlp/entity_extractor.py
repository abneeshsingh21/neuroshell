# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell NLP Entity Extractor — Production Grade
Git ref, Docker entity, IP/port, regex pattern, environment variable extraction.
"""

import re
from dataclasses import dataclass, field

try:
    import spacy
    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False


@dataclass
class ExtractedEntity:
    entity_type: str  # FILE_PATH, PACKAGE, URL, NUMBER, COMMAND, DIRECTORY, GIT_REF, DOCKER, IP, PORT, ENV_VAR, REGEX
    value: str
    start: int = 0
    end: int = 0
    confidence: float = 0.9


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    has_entities: bool = False

    @property
    def paths(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "FILE_PATH"]

    @property
    def packages(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "PACKAGE"]

    @property
    def urls(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "URL"]

    @property
    def numbers(self) -> list[int]:
        return [int(e.value) for e in self.entities if e.entity_type == "NUMBER"]

    @property
    def commands(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "COMMAND"]

    @property
    def directories(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "DIRECTORY"]

    @property
    def git_refs(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "GIT_REF"]

    @property
    def docker_entities(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "DOCKER"]

    @property
    def ips(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "IP"]

    @property
    def ports(self) -> list[int]:
        return [int(e.value) for e in self.entities if e.entity_type == "PORT"]

    @property
    def env_vars(self) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == "ENV_VAR"]

    def by_type(self, entity_type: str) -> list[str]:
        return [e.value for e in self.entities if e.entity_type == entity_type]

    def summary(self) -> str:
        if not self.entities:
            return "No entities found"
        parts = [f"{e.entity_type}: {e.value}" for e in self.entities]
        return "; ".join(parts)


class EntityExtractor:
    """
    Production-grade entity extractor.

    Extracts:
    - File paths (Windows + Unix)
    - URLs, packages, numbers
    - Git refs (branches, SHAs, tags)
    - Docker entities (image:tag, containers)
    - IP addresses and ports
    - Environment variables
    - Regex patterns
    - Commands and directories
    """

    # ── File paths ──
    PATH_PATTERN = re.compile(
        r"""(?:
            [A-Za-z]:\\[\w\\\-\.]+      |
            /[\w/\-\.]+                  |
            \.{1,2}/[\w/\-\.]+           |
            \b[\w\-]+\.(?:py|js|ts|cpp|c|h|java|go|rs|rb|
                         txt|md|json|yaml|yml|toml|xml|html|
                         css|sh|bat|ps1|sql|csv|log|conf|cfg|
                         dockerfile|makefile|gitignore|env|
                         tsx|jsx|vue|svelte|tf|hcl|proto|graphql)
        )""",
        re.VERBOSE | re.IGNORECASE,
    )

    # ── URLs ──
    URL_PATTERN = re.compile(
        r"https?://[\w\-\.]+[\w/\-\.~:?#\[\]@!$&'()*+,;=%]+|"
        r"(?:github|gitlab|bitbucket)\.com/[\w\-\.]+/[\w\-\.]+",
        re.IGNORECASE,
    )

    # ── Packages ──
    PACKAGE_CONTEXT = re.compile(
        r"(?:install|add|require|import|uninstall|remove)\s+([\w\-]+(?:\s+[\w\-]+)*)",
        re.IGNORECASE,
    )

    # ── Numbers ──
    NUMBER_PATTERN = re.compile(
        r"\b(\d+)\s*(?:lines?|files?|mb|gb|kb|bytes?|items?|rows?|"
        r"minutes?|seconds?|hours?|days?|times?|processes?|ports?|threads?)\b",
        re.IGNORECASE,
    )
    PLAIN_NUMBER = re.compile(r"\b(?:last|top|first|show|head|tail)\s+(\d+)\b", re.IGNORECASE)

    # ── Directories ──
    DIR_PATTERN = re.compile(
        r"(?:go\s+to|navigate\s+to|cd\s+to|open|switch\s+to)\s+"
        r"(?:the\s+)?(?:my\s+)?([\w\-]+)\s*(?:folder|directory|dir)?",
        re.IGNORECASE,
    )

    # ── Commands ──
    COMMAND_PATTERN = re.compile(
        r"(?:run|execute|start|use|the)\s+(?:the\s+)?"
        r"(git|pip|npm|docker|python|pytest|node|cargo|kubectl|"
        r"terraform|make|cmake|gcc|flask|django|uvicorn|go|rustc|helm)\s*(?:command)?",
        re.IGNORECASE,
    )

    # ── Git refs ──
    GIT_BRANCH = re.compile(
        r"(?:branch|checkout|merge|rebase|switch)\s+(?:to\s+)?"
        r"([a-zA-Z][\w\-\.\/]+)",
        re.IGNORECASE,
    )
    GIT_SHA = re.compile(r"\b([0-9a-f]{7,40})\b")
    GIT_TAG = re.compile(r"\b(v?\d+\.\d+\.\d+(?:-[\w\.]+)?)\b")

    # ── Docker ──
    DOCKER_IMAGE = re.compile(
        r"(?:image|container|run|pull|push)\s+"
        r"([\w\-\.]+(?:/[\w\-\.]+)*(?::[\w\-\.]+)?)",
        re.IGNORECASE,
    )

    # ── IP/Port ──
    IP_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
    PORT_PATTERN = re.compile(r"(?:port|:)\s*(\d{2,5})\b", re.IGNORECASE)

    # ── Environment variables ──
    ENV_VAR = re.compile(r"\$\{?([A-Z_][A-Z0-9_]+)\}?")

    def __init__(self):
        self._nlp = None
        self._loaded = False

    def initialize(self) -> bool:
        if not HAS_SPACY:
            return False
        try:
            self._nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
            self._loaded = True
            return True
        except OSError:
            return False

    def extract(self, text: str) -> ExtractionResult:
        """Extract all entity types from text."""
        result = ExtractionResult()

        extractors = [
            self._extract_urls,
            self._extract_paths,
            self._extract_packages,
            self._extract_numbers,
            self._extract_directories,
            self._extract_commands,
            self._extract_git_refs,
            self._extract_docker,
            self._extract_ips,
            self._extract_ports,
            self._extract_env_vars,
        ]

        for extractor in extractors:
            result.entities.extend(extractor(text))

        if self._nlp:
            result.entities.extend(self._extract_spacy(text))

        # Deduplicate
        seen = set()
        unique = []
        for entity in result.entities:
            key = (entity.entity_type, entity.value)
            if key not in seen:
                seen.add(key)
                unique.append(entity)
        result.entities = unique
        result.has_entities = len(unique) > 0

        return result

    def _extract_urls(self, text: str) -> list[ExtractedEntity]:
        return [ExtractedEntity("URL", m.group(), m.start(), m.end()) for m in self.URL_PATTERN.finditer(text)]

    def _extract_paths(self, text: str) -> list[ExtractedEntity]:
        entities = []
        for m in self.PATH_PATTERN.finditer(text):
            if "://" in text[max(0, m.start()-10):m.start()]:
                continue
            entities.append(ExtractedEntity("FILE_PATH", m.group().strip(), m.start(), m.end()))
        return entities

    def _extract_packages(self, text: str) -> list[ExtractedEntity]:
        entities = []
        for m in self.PACKAGE_CONTEXT.finditer(text):
            for part in re.split(r"\s+and\s+|\s*,\s*|\s+", m.group(1)):
                part = part.strip()
                if part and len(part) > 1 and not part.isdigit():
                    entities.append(ExtractedEntity("PACKAGE", part, m.start(), m.end()))
        return entities

    def _extract_numbers(self, text: str) -> list[ExtractedEntity]:
        entities = []
        for pattern in [self.NUMBER_PATTERN, self.PLAIN_NUMBER]:
            for m in pattern.finditer(text):
                entities.append(ExtractedEntity("NUMBER", m.group(1), m.start(), m.end()))
        return entities

    def _extract_directories(self, text: str) -> list[ExtractedEntity]:
        return [ExtractedEntity("DIRECTORY", m.group(1), m.start(), m.end()) for m in self.DIR_PATTERN.finditer(text)]

    def _extract_commands(self, text: str) -> list[ExtractedEntity]:
        return [ExtractedEntity("COMMAND", m.group(1).lower(), m.start(), m.end()) for m in self.COMMAND_PATTERN.finditer(text)]

    def _extract_git_refs(self, text: str) -> list[ExtractedEntity]:
        entities = []
        for m in self.GIT_BRANCH.finditer(text):
            entities.append(ExtractedEntity("GIT_REF", m.group(1), m.start(), m.end(), 0.85))
        for m in self.GIT_SHA.finditer(text):
            val = m.group(1)
            if len(val) >= 7 and not val.isdigit():
                entities.append(ExtractedEntity("GIT_REF", val, m.start(), m.end(), 0.9))
        for m in self.GIT_TAG.finditer(text):
            entities.append(ExtractedEntity("GIT_REF", m.group(1), m.start(), m.end(), 0.85))
        return entities

    def _extract_docker(self, text: str) -> list[ExtractedEntity]:
        return [ExtractedEntity("DOCKER", m.group(1), m.start(), m.end(), 0.8) for m in self.DOCKER_IMAGE.finditer(text)]

    def _extract_ips(self, text: str) -> list[ExtractedEntity]:
        entities = []
        for m in self.IP_PATTERN.finditer(text):
            parts = m.group(1).split(".")
            if all(0 <= int(p) <= 255 for p in parts):
                entities.append(ExtractedEntity("IP", m.group(1), m.start(), m.end()))
        return entities

    def _extract_ports(self, text: str) -> list[ExtractedEntity]:
        entities = []
        for m in self.PORT_PATTERN.finditer(text):
            port = int(m.group(1))
            if 1 <= port <= 65535:
                entities.append(ExtractedEntity("PORT", m.group(1), m.start(), m.end()))
        return entities

    def _extract_env_vars(self, text: str) -> list[ExtractedEntity]:
        return [ExtractedEntity("ENV_VAR", m.group(1), m.start(), m.end(), 0.95) for m in self.ENV_VAR.finditer(text)]

    def _extract_spacy(self, text: str) -> list[ExtractedEntity]:
        entities = []
        try:
            doc = self._nlp(text)
            for ent in doc.ents:
                if ent.label_ in ("CARDINAL", "QUANTITY") and ent.text.isdigit():
                    entities.append(ExtractedEntity("NUMBER", ent.text, ent.start_char, ent.end_char, 0.8))
        except Exception:
            pass
        return entities
