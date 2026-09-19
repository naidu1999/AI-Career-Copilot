from backend.jobs.matcher import match_job
from backend.services.profile_parser import parse_resume
from fastapi.testclient import TestClient
from backend.main import app

def test_parser_preserves_unknown_and_skills():
    result=parse_resume("Jane Doe\njane@example.com\nSKILLS\nPython, SQL\nEXPERIENCE\nBuilt pipelines")
    assert result["skills"]==["Python","SQL"]
    assert "Jane Doe" in result["unknown_content"]
    assert result["personal_details"]["email"]=="jane@example.com"

def test_bulk_applications_idempotent(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"test.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    from backend.db.local import execute,now,uid
    with TestClient(app) as client:
        ids=[]
        for t in ("Data Scientist","ML Engineer"):
            jid=uid();ids.append(jid)
            execute("INSERT INTO jobs (id,source_key,provider,source_name,title,company,location,description,url,posted_at,first_seen_at,date_semantics,employment_type,is_active,raw_json,last_seen_at,liveness_status,canonical_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,jid[:8],"manual","Test",t,"Acme","Bengaluru","Python","https://example.com/job","2026-09-17",now(),"standardized","full-time",1,"{}",now(),"unknown",""))
        r=client.post("/api/applications/bulk",json=[{"job_id":ids[0],"status":"applied"},{"job_id":ids[1],"status":"saved"}])
        assert r.status_code==201 and r.json()["added"]==2
        # Re-posting the same jobs must not duplicate rows or downgrade statuses.
        r2=client.post("/api/applications/bulk",json=[{"job_id":ids[0],"status":"saved"},{"job_id":ids[1],"status":"saved"}])
        assert r2.status_code==201 and r2.json()["added"]==0
        apps=client.get("/api/applications").json()
        assert len(apps)==2
        assert {a["status"] for a in apps}=={"applied","saved"}
        # Unknown jobs are refused rather than silently skipped.
        assert client.post("/api/applications/bulk",json=[{"job_id":"missing-job"}]).status_code==400


def test_contact_and_answer_sheet_and_gap(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"test.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    from backend.db.local import execute,now,uid
    with TestClient(app) as client:
        # Blank contact fields must not erase saved values.
        r=client.patch("/api/profile/contact",json={"phone":"+91 90000 00000","location_current":"Hyderabad"})
        assert r.status_code==200
        r2=client.patch("/api/profile/contact",json={"expected_compensation":"12 LPA"})
        assert r2.status_code==200
        prof=client.get("/api/profile").json()
        assert prof["phone"]=="+91 90000 00000" and prof["location_current"]=="Hyderabad"
        assert client.put("/api/profile",json={"skills":["Python","SQL","docker"],"target_titles":["Python Developer"]}).status_code==200
        jid=uid()
        execute("INSERT INTO jobs (id,source_key,provider,source_name,title,company,location,description,url,posted_at,first_seen_at,date_semantics,employment_type,is_active,raw_json,last_seen_at,liveness_status,canonical_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,jid[:8],"manual","Test","Python Developer","Acme","Bengaluru","We need Python and SQL and docker experience","https://example.com/x","2026-09-17",now(),"standardized","full-time",1,"{}",now(),"unknown",""))
        gap=client.post(f"/api/jobs/{jid}/gap").json()
        assert "python" in gap["have"] and gap["skills_overlap_pct"]>=0
        assert isinstance(gap["jd_terms_missing"],list)
        aid=client.post("/api/applications",json={"job_id":jid,"status":"applied"}).json()["id"]
        sheet=client.get(f"/api/applications/{aid}/answer-sheet").json()
        assert sheet["contact"]["phone"]=="+91 90000 00000"
        assert any(c["label"].startswith("Phone") for c in sheet["checklist"])


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
        # Deletion demands an explicit confirm token (typed by the user).
        assert client.delete("/api/profiles/priya").status_code==400
        gone=client.delete("/api/profiles/priya?confirm=priya")
        assert gone.status_code==200
        assert client.get("/api/profile").json()["id"]=="default"
        assert client.get("/api/profiles").json() and client.get("/api/profiles").json()[0]["id"]=="default"
        # Deleting the last remaining profile is refused.
        assert client.delete("/api/profiles/default").status_code==400
        # With another profile present, default is deletable: it resets to a
        # clean workspace instead of vanishing, and the switch falls back.
        client.post("/api/profiles",json={"id":"arjun","full_name":"Arjun Rao"})
        client.post("/api/session/profile",json={"profile_id":"default"})
        wiped=client.delete("/api/profiles/default?confirm=default")
        assert wiped.status_code==200
        assert client.get("/api/profile").json()["id"]=="default"
        reset=client.get("/api/profile").json()
        assert reset["full_name"]=="Default profile" and reset["target_titles"]==[]

def test_dossier_storybank_and_intel(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"test.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    from backend.services.dossier import basic_dossier, legitimacy_check, parse_dossier_json
    # Legitimacy is score-neutral and flags financial-scam wording.
    scam=legitimacy_check({"provider":"adzuna","posted_at":"","repost_count":0,"duplicate_count":0,"description":"Pay registration fee. WhatsApp only.","company":"X","url":""})
    assert scam["assessment"] in {"unclear","questionable"}
    # An estimated requirement can never be critical; verdict parsing is strict.
    d=parse_dossier_json('{"global_score":4.7,"verdict":"PRIORITIZE","dimensions":{},"requirements":[{"requirement":"5 yrs Rust","weight":"critical","basis":"estimated"}]}')
    assert d["verdict"]=="prioritize" and d["requirements"][0]["weight"]=="helpful" and d["requirements"][0]["basis"]=="estimated"
    fallback=basic_dossier({"title":"Data Scientist"},{},{"components":{"title":85},"missing_skills":["Spark"],"classification":"qualified","score":82})
    assert 1<=fallback["global_score"]<=5 and fallback["verdict"] in {"prioritize","strong","possible","skip"}
    with TestClient(app) as client:
        # Story bank CRUD.
        made=client.post("/api/stories",json={"title":"Led migration","category":"leadership","situation":"Legacy on-prem","task":"Move 40 services","action":"Phased cutover","result":"Zero downtime","status":"ready","tags":["cloud"]})
        assert made.status_code==201
        stories=client.get("/api/stories").json()
        assert stories and stories[0]["title"]=="Led migration" and stories[0]["tags"]==["cloud"]
        sid=stories[0]["id"]
        assert client.put(f"/api/stories/{sid}",json={"title":"Led migration","status":"ready"}).status_code==200
        # Dossier falls back to the deterministic engine when AI is unconfigured.
        client.post("/api/jobs/manual",json={"title":"Data Scientist","company":"Acme","location":"Bengaluru","url":"https://acme.jobs/1","description":"Python, SQL"})
        jobs=client.get("/api/jobs",params={"classification":"all","strict_date":"false","minimum_score":0,"hours":720}).json()["items"];assert jobs,"manual job should be listed"
        dossier=client.post(f"/api/dossier/{jobs[0]['id']}")
        assert dossier.status_code==201 and dossier.json()["dossier"]["source"]=="basic"
        assert client.get(f"/api/dossier/{jobs[0]['id']}").json()["dossier"]["verdict"] in {"prioritize","strong","possible","skip"}
        # Pipeline intel responds with funnel structure.
        intel=client.get("/api/pipeline/intel").json()
        assert intel["total"]==0 and "overdue_followups" in intel and intel["stories_ready"]==1
        assert client.delete(f"/api/stories/{sid}").status_code==200

def test_v04_manual_job_match_and_application(tmp_path, monkeypatch):
    from backend.core.config_new import settings
    monkeypatch.setattr(settings,"DATABASE_PATH",str(tmp_path/"v04.db"))
    monkeypatch.setattr(settings,"UPLOAD_DIR",str(tmp_path/"uploads"))
    with TestClient(app) as client:
        job={"title":"Data Scientist","company":"Example","location":"Bengaluru",
             "description":"Python SQL, 2 years experience","url":"https://example.com/jobs/1",
             "employment_type":"full-time"}
        assert client.post("/api/jobs/manual",json=job).status_code==201
        from time import monotonic, sleep
        deadline=monotonic()+10
        matches=[]
        while monotonic()<deadline:
            matches=client.get("/api/jobs",params={"classification":"all","strict_date":"false","minimum_score":0,"hours":720}).json()["items"]
            if matches:break
            sleep(0.2)
        assert matches,"background re-match should produce the manual job's match"
        matches=client.get("/api/jobs?classification=all&strict_date=false&hours=720").json()["items"]
        assert len(matches)==1 and matches[0]["matcher_version"]=="4.1"
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
