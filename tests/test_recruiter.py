from backend.services.recruiter import recruiter_specialism, senior_recruiter_system_prompt


def test_job_title_drives_recruiter_specialism():
    assert recruiter_specialism({"title": "Data Analyst"}, {"target_titles": ["ML Engineer"]}) == "Data Analyst"


def test_profile_target_is_fallback_specialism():
    assert recruiter_specialism({}, {"target_titles": ["Computer Vision Engineer"]}) == "Computer Vision Engineer"


def test_prompt_has_experience_and_truthfulness_guardrails():
    prompt = senior_recruiter_system_prompt({"title": "Data Analyst"}, {"target_titles": []})
    assert "20+ years" in prompt
    assert "Data Analyst" in prompt
    assert "Do not claim real employment" in prompt
    assert "Never invent a qualification" in prompt
