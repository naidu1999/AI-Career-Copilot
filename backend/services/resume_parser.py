import re
from typing import Any


SECTION_HEADINGS = {
    "summary": [
        "professional summary",
        "career summary",
        "profile summary",
        "summary",
        "objective",
    ],
    "skills": [
        "technical skills",
        "core skills",
        "key skills",
        "skills",
        "technologies",
    ],
    "experience": [
        "professional experience",
        "work experience",
        "employment history",
        "experience",
    ],
    "education": [
        "education",
        "academic background",
        "qualifications",
    ],
    "projects": [
        "key projects",
        "academic projects",
        "personal projects",
        "projects",
    ],
    "certifications": [
        "education & certifications",
        "certifications",
        "certificates",
    ],
}


class ResumeParser:

    @staticmethod
    def _normalize_heading(text: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z& ]", "", text)
        return re.sub(r"\s+", " ", cleaned).strip().lower()

    @staticmethod
    def _identify_section(line: str) -> str | None:
        normalized_line = ResumeParser._normalize_heading(line)

        for section_name, headings in SECTION_HEADINGS.items():
            if normalized_line in headings:
                return section_name

        return None

    @staticmethod
    def _split_items(text: str) -> list[str]:
        items = re.split(r"[\n,;•|]+", text)

        return [
            item.strip(" -:\t")
            for item in items
            if item.strip(" -:\t")
        ]

    @staticmethod
    def _create_raw_entries(text: str) -> list[dict[str, Any]]:
        blocks = re.split(
            r"\n\s*\n|(?=\n[A-Z][^\n]{2,80}\n)",
            text,
        )

        entries: list[dict[str, Any]] = []

        for block in blocks:
            cleaned = block.strip()

            if cleaned:
                entries.append({
                    "raw_text": cleaned,
                })

        return entries

    def parse(self, resume_text: str) -> dict[str, Any]:
        sections = {
            "summary": "",
            "skills": "",
            "experience": "",
            "education": "",
            "projects": "",
            "certifications": "",
        }

        current_section: str | None = None
        unclassified_lines: list[str] = []

        for raw_line in resume_text.splitlines():
            line = raw_line.strip()

            if not line:
                if current_section:
                    sections[current_section] += "\n"
                continue

            detected_section = self._identify_section(line)

            if detected_section:
                current_section = detected_section
                continue

            if current_section:
                sections[current_section] += line + "\n"
            else:
                unclassified_lines.append(line)

        summary = sections["summary"].strip()

        if not summary and unclassified_lines:
            summary = " ".join(unclassified_lines[:5])

        return {
            "summary": summary or None,
            "skills": self._split_items(sections["skills"]),
            "experience": self._create_raw_entries(
                sections["experience"]
            ),
            "education": self._create_raw_entries(
                sections["education"]
            ),
            "projects": self._create_raw_entries(
                sections["projects"]
            ),
            "certifications": self._create_raw_entries(
                sections["certifications"]
            ),
        }