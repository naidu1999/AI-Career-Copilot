from backend.jobs.matcher import match_job
from backend.services.profile_parser import parse_resume
from fastapi.testclient import TestClient
from backend.main import app

def test_parser_preserves_unknown_and_skills():
    result=parse_resume("Jane Doe\njane@example.com\nSKILLS\nPython, SQL\nEXPERIENCE\nBuilt pipelines")
    assert result["skills"]==["Python","SQL"]
    assert "Jane Doe" in result["unknown_content"]
    assert result["personal_details"]["email"]=="jane@example.com"

def test_matching_and_exclusion():
    p={"target_titles":["Data Scientist"],"skills":["Python","SQL"],"locations":["Bengaluru"],"remote_allowed":True,"remote_countries":["India"],"years_experience":3,"excluded_roles":["Sales"],"excluded_employment_types":["contract"]}
    good=match_job(p,{"title":"Data Scientist","description":"Python and SQL","location":"Bengaluru","employment_type":"full-time"})
    bad=match_job(p,{"title":"Sales Data Scientist","description":"Python","location":"Remote","employment_type":"full-time"})
    assert good["score"]>80
    assert bad["excluded"] is True

def test_location_and_experience_are_hard_eligibility_checks():
    p={"target_titles":["ML Engineer"],"skills":["Python"],"locations":["Bengaluru"],"remote_allowed":True,"remote_countries":["India"],"years_experience":2}
    abroad=match_job(p,{"title":"ML Engineer","description":"Python","location":"São Paulo","employment_type":"full-time"})
    senior=match_job(p,{"title":"Senior ML Engineer","description":"Requires 7+ years Python","location":"Bengaluru","employment_type":"full-time"})
    assert abroad["score"] <= 35 and abroad["excluded"]
    assert senior["score"] <= 35 and any("7 years" in x for x in senior["warnings"])

def test_application_boots_and_profile_exists(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"test.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code==200
        response=client.get("/api/profile")
        assert response.status_code==200
        assert "Data Scientist" in response.json()["target_titles"]
        detected=client.post("/api/sources/detect",json={"name":"Example","careers_url":"https://jobs.ashbyhq.com/example"})
        assert detected.json()["provider"]=="ashby"
        assert client.post("/api/sources/detect",json={"name":"Bad","careers_url":"http://evil.test/x"}).status_code==400

def test_local_multiuser_profiles(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"test.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    with TestClient(app) as client:
        created=client.post("/api/profiles",json={"id":"priya","full_name":"Priya Sharma"})
        assert created.status_code==201
        listed=client.get("/api/profiles").json()
        assert {"default","priya"} <= {p["id"] for p in listed}
        switched=client.post("/api/session/profile",json={"profile_id":"priya"})
        assert switched.status_code==200
        assert client.get("/api/profile").json()["id"]=="priya"
        dup=client.post("/api/profiles",json={"id":"priya"})
        assert dup.status_code==409
        bad=client.post("/api/profiles",json={"id":"bad id!"})
        assert bad.status_code==422
        gone=client.delete("/api/profiles/priya")
        assert gone.status_code==200
        assert client.get("/api/profile").json()["id"]=="default"
        assert client.delete("/api/profiles/default").status_code==400

def test_v04_manual_job_match_and_application(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"v04.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    with TestClient(app) as client:
        job={"title":"Data Scientist","company":"Example","location":"Bengaluru",
             "description":"Python SQL, 2 years experience","url":"https://example.com/jobs/1",
             "employment_type":"full-time"}
        assert client.post("/api/jobs/manual",json=job).status_code==201
        matches=client.get("/api/jobs?classification=all&strict_date=false&hours=720").json()
        assert len(matches)==1 and matches[0]["matcher_version"]=="4.0"
        assert set(matches[0]["components"]) >= {"title","skills","location","experience"}
        assert client.post("/api/applications",json={"job_id":matches[0]["id"],"status":"shortlisted"}).status_code==201
        assert client.get("/api/applications").json()[0]["status"]=="shortlisted"

def test_v04_recommended_sources_are_safe_by_default(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"sources.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    monkeypatch.setattr(settings,"ADZUNA_APP_ID","")
    monkeypatch.setattr(settings,"JOOBLE_API_KEY","")
    with TestClient(app) as client:
        assert client.post("/api/sources/seed").status_code==200
        sources=client.get("/api/sources").json()
        assert next(x for x in sources if x["provider"]=="usajobs")["enabled"]==0
        assert all(x["enabled"]==0 for x in sources if x["provider"] in {"greenhouse","lever"})

def test_v1_indexes_and_protected_scheduler(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    from backend.db.local import connection
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"indexed.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    monkeypatch.setattr(settings,"CRON_SECRET","test-only-secret")
    with TestClient(app) as client:
        assert client.post("/api/system/scheduled-scan").status_code==401
        with connection() as db:
            indexes={row[1] for row in db.execute("PRAGMA index_list(job_matches)")}
        assert "idx_matches_profile_class_score" in indexes

def test_hosted_users_are_isolated(tmp_path, monkeypatch):
    import backend.main as main_module
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"hosted.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    monkeypatch.setattr(settings,"DEPLOYMENT_MODE","hosted")
    monkeypatch.setattr(settings,"PUBLIC_BASE_URL","https://karna.test")
    async def fake_auth(token):
        return {"id":token,"email":f"{token}@example.com"}
    monkeypatch.setattr(main_module,"authenticate",fake_auth)
    with TestClient(app,base_url="https://karna.test") as client:
        assert client.get("/api/profile").status_code==401
        client.cookies.set(settings.SESSION_COOKIE_NAME,"user-a")
        a=client.get("/api/profile");assert a.status_code==200
        profile=a.json();profile["full_name"]="User A"
        assert client.put("/api/profile",json=profile).status_code==200
        assert client.post("/api/sources",json={"name":"A board","provider":"greenhouse","board_key":"shared"}).status_code==201
        assert client.post("/api/sources",headers={"Origin":"https://evil.example"},json={"name":"Blocked","provider":"lever","board_key":"blocked"}).status_code==403
        client.cookies.set(settings.SESSION_COOKIE_NAME,"user-b")
        b=client.get("/api/profile");assert b.status_code==200 and b.json()["full_name"]==""
        assert client.get("/api/sources").json()==[]
        assert client.post("/api/sources",json={"name":"B board","provider":"greenhouse","board_key":"shared"}).status_code==201
        client.cookies.set(settings.SESSION_COOKIE_NAME,"user-a")
        assert client.get("/api/profile").json()["full_name"]=="User A"
        assert [x["name"] for x in client.get("/api/sources").json()]==["A board"]
