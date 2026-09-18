"""Optional LinkedIn profile import via ScrapingDog.

Karna OS never scrapes job portals and never auto-applies; this module exists
for one opt-in purpose: pulling YOUR OWN public profile into your career
evidence so profile fields can be pre-filled. It requires the user's personal
ScrapingDog API key (SCRAPINGDOG_API_KEY in .env) and does nothing when it is
missing. Keys are never persisted to the database or logs.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from backend.core.config_new import settings

_PROFILE_ID = re.compile(r"/in/([^/?#]+)")


def configured() -> bool:
    return bool(settings.SCRAPINGDOG_API_KEY)


def extract_profile_id(value: str) -> str:
    """Accept a full LinkedIn URL or a bare profile id."""
    value = (value or "").strip()
    match = _PROFILE_ID.search(value)
    pid = match.group(1) if match else value
    return re.sub(r"[/?#].*$", "", pid).strip()


async def fetch_profile(url_or_id: str) -> dict[str, Any]:
    """Fetch a LinkedIn profile through ScrapingDog and return the parsed JSON."""
    if not configured():
        raise RuntimeError("ScrapingDog is not configured in .env (SCRAPINGDOG_API_KEY)")
    profile_id = extract_profile_id(url_or_id)
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", profile_id):
        raise ValueError("That does not look like a LinkedIn profile id")
    url = "https://api.scrapingdog.com/linkedin"
    params = {
        "api_key": settings.SCRAPINGDOG_API_KEY,
        "type": "profile",
        "linkId": profile_id,
        "premium": "true",
    }
    async with httpx.AsyncClient(timeout=40, follow_redirects=False) as client:
        response = await client.get(url, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Never echo the key back in errors.
            raise RuntimeError(f"ScrapingDog request failed ({exc.response.status_code})") from exc
        raw = response.content
    # LinkedIn payloads sometimes contain control characters that break JSON
    # parsing; strip them like the reference recipe does.
    cleaned = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b"", raw)
    data: Any
    try:
        data = __import__("json").loads(cleaned)
    except Exception as exc:  # pragma: no cover - depends on upstream payload
        raise RuntimeError("ScrapingDog returned an unreadable response") from exc
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict) or data.get("message") and not data.get("fullName"):
        raise RuntimeError(str((data or {}).get("message") or "Profile could not be fetched"))
    return data


def to_profile_fields(profile: dict[str, Any]) -> dict[str, Any]:
    """Map a LinkedIn payload onto Karna OS profile fields.

    Everything lands as *suggestions* — nothing is written until the user
    reviews and saves. Numbers and dates are deliberately conservative.
    """
    experiences = profile.get("experience") or []

    def _years() -> float:
        spans = []
        for exp in experiences:
            start = str(exp.get("date_range") or exp.get("dateRange") or "")
            numbers = [int(n) for n in re.findall(r"(19|20)\d{2}", start)]
            if numbers:
                spans.append(min(numbers))
        if not spans:
            return 0.0
        # Most recent listed start year is the earliest we can safely infer
        # conservatively: use the OLDEST listed start as career start.
        earliest = min(spans)
        current_year = 2026
        return max(0.0, float(current_year - earliest))

    headline = profile.get("headline") or ""
    titles = []
    for exp in experiences[:3]:
        title = exp.get("title")
        if title:
            titles.append(title)
    skills = profile.get("skills") or []
    return {
        "full_name": profile.get("fullName") or profile.get("full_name") or "",
        "headline": headline,
        "location": profile.get("location") or profile.get("location_name") or "",
        "about": profile.get("about") or "",
        "current_role": (experiences[0].get("title") if experiences else "") or "",
        "current_employer": (experiences[0].get("company_name") or exp_employer(experiences) or ""),
        "suggested_titles": titles,
        "suggested_skills": [s for s in skills if isinstance(s, str)][:30],
        "suggested_years_experience": _years(),
        "experience": [
            {
                "title": e.get("title", ""),
                "company": e.get("company_name", ""),
                "date_range": e.get("date_range") or e.get("dateRange", ""),
                "description": (e.get("description") or "")[:600],
            }
            for e in experiences[:8]
        ],
        "education": [
            {
                "degree": (e.get("degree") or ""),
                "field": (e.get("field_of_study") or ""),
                "school": (e.get("school") or ""),
            }
            for e in (profile.get("education") or [])[:4]
        ],
    }


def exp_employer(experiences: list) -> str:
    return (experiences[0].get("company_name") or "") if experiences else ""
