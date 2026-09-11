import re
from typing import Any


HEADINGS = {
    "summary": {"summary", "professional summary", "profile", "objective"},
    "skills": {"skills", "technical skills", "core competencies", "technologies"},
    "experience": {"experience", "work experience", "professional experience", "employment"},
    "education": {"education", "academic background", "qualifications"},
    "projects": {"projects", "key projects", "personal projects", "academic projects"},
    "certifications": {"certifications", "certificates", "licenses"},
    "achievements": {"achievements", "awards", "honors"},
}


def norm(value: str) -> str:
    return re.sub(r"[^a-z& ]", "", value.lower()).strip()


def parse_resume(text: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {k: [] for k in HEADINGS}
    unknown: list[str] = []
    current: str | None = None
    lookup = {h: k for k, hs in HEADINGS.items() for h in hs}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        section = lookup.get(norm(line))
        if section:
            current = section
        elif current:
            sections[current].append(line)
        else:
            unknown.append(line)
    skills = []
    for line in sections["skills"]:
        skills.extend(x.strip(" -•") for x in re.split(r"[,;|•]", line) if x.strip(" -•"))
    personal = {
        "email": next(iter(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)), ""),
        "phone": next(iter(re.findall(r"(?:\+?\d[\d\s-]{8,}\d)", text)), ""),
        "links": re.findall(r"https?://\S+|(?:linkedin\.com|github\.com)/\S+", text, re.I),
    }
    return {
        "personal_details": personal,
        "summary": " ".join(sections["summary"]),
        "skills": list(dict.fromkeys(skills)),
        "experience": [{"raw_text": x} for x in sections["experience"]],
        "education": [{"raw_text": x} for x in sections["education"]],
        "projects": [{"raw_text": x} for x in sections["projects"]],
        "certifications": [{"raw_text": x} for x in sections["certifications"]],
        "achievements": [{"raw_text": x} for x in sections["achievements"]],
        "unknown_content": unknown,
        "parser": {"type": "rules", "version": "1.0", "requires_review": True},
    }

