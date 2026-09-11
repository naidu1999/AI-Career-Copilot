import json


def recruiter_specialism(job: dict, profile: dict) -> str:
    """Choose the recruiting discipline from the vacancy, falling back to profile targets."""
    title = str(job.get("title") or "").strip()
    targets = [str(value).strip() for value in profile.get("target_titles", []) if str(value).strip()]
    return title or (targets[0] if targets else "the candidate's selected career path")


def senior_recruiter_system_prompt(job: dict, profile: dict) -> str:
    role = recruiter_specialism(job, profile)
    return (
        "You are Karna OS Senior Recruiter Mode. Simulate the rigorous judgment and "
        "coaching approach expected from a highly experienced recruiter with 20+ years "
        f"of hiring exposure, specializing in {role}. Do not claim real employment, "
        "personal memories, privileged employer knowledge, or guaranteed hiring outcomes. "
        "Evaluate the candidate as both an ATS reviewer and a human recruiter. Separate "
        "mandatory requirements from preferences; assess title, seniority, relevant years, "
        "skills, location, work authorization, evidence strength, communication, and likely "
        "interview risk. Be candid, specific, practical, bias-aware, and evidence-grounded. "
        "Never invent a qualification. Label uncertainty and explain every recommendation."
    )


def recruiter_context(job: dict, profile: dict, verified: list[dict]) -> str:
    safe_profile = {
        "current_role": profile.get("current_role"),
        "target_titles": profile.get("target_titles", []),
        "years_experience": profile.get("years_experience", 0),
        "relevant_experience": profile.get("relevant_experience", 0),
        "locations": profile.get("locations", []),
        "country": profile.get("country"),
        "remote_countries": profile.get("remote_countries", []),
        "work_authorization": profile.get("work_authorization"),
        "needs_sponsorship": profile.get("needs_sponsorship", False),
        "notice_period_days": profile.get("notice_period_days"),
    }
    return (
        f"TARGET ROLE SPECIALISM: {recruiter_specialism(job, profile)}\n"
        f"CAREER PROFILE: {json.dumps(safe_profile)}\n"
        f"VERIFIED EVIDENCE: {json.dumps(verified)}"
    )
