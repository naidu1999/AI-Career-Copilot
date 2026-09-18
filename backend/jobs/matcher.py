"""Karna OS deterministic, auditable Matching Engine v4."""
import re

VERSION="4.1"
SENIORITY={"intern":0,"trainee":0,"junior":1,"associate":1,"entry":1,"mid":2,"senior":3,"lead":4,"staff":4,"principal":5,"head":6,"director":6,"manager":4}
REMOTE_GLOBAL=("worldwide","anywhere","global","work from anywhere")
STOP={"and","the","with","for","from","you","our","engineer","developer","specialist","analyst"}
ROLE_FAMILIES={
 "data_analytics":{"data analyst","business intelligence","bi analyst","analytics analyst","reporting analyst","power bi","tableau"},
 "data_science":{"data scientist","applied scientist","decision scientist","research scientist","predictive analytics"},
 "machine_learning":{"machine learning","ml engineer","ai engineer","artificial intelligence","applied ml","mlops","model evaluation"},
 "data_engineering":{"data engineer","analytics engineer","etl","big data","spark engineer","data platform"},
 "nlp_genai":{"nlp","natural language processing","generative ai","genai","llm","rag engineer","prompt engineer","agentic ai"},
 "computer_vision":{"computer vision","cv engineer","image processing","vision engineer","opencv"},
 "software":{"software engineer","full stack","backend","frontend","web developer","mobile developer","devops","site reliability"},
 "product":{"product manager","program manager","project manager","scrum master"},
 "sales_support":{"sales","business development","customer support","technical support","bpo","call center"},
 "finance":{"finance","accountant","audit","tax","investment banking"},
 "hr":{"human resources","recruiter","talent acquisition","hr business"},
}
RELATED={
 "data_analytics":{"data_science","data_engineering"},"data_science":{"data_analytics","machine_learning","nlp_genai","computer_vision"},
 "machine_learning":{"data_science","nlp_genai","computer_vision","software"},"data_engineering":{"data_analytics","software"},
 "nlp_genai":{"machine_learning","data_science"},"computer_vision":{"machine_learning","data_science"},"software":{"machine_learning","data_engineering"},
}
SYNONYMS={
 "machine learning":{"ml","machine learning"},"artificial intelligence":{"ai","artificial intelligence"},
 "generative ai":{"genai","generative ai","llm"},"natural language processing":{"nlp","natural language processing"},
 "computer vision":{"cv","computer vision","opencv"},"power bi":{"powerbi","power bi"},
 "postgresql":{"postgres","postgresql"},"amazon web services":{"aws","amazon web services"},
}

def tokens(text:str)->set[str]:
 return {x for x in re.findall(r"[a-z0-9+#.]{2,}",(text or "").lower()) if x not in STOP}

def normalize(text:str)->str:
 return " ".join(re.findall(r"[a-z0-9+#.]+",(text or "").lower()))

def skill_present(skill:str,text_tokens:set[str])->bool:
 st=tokens(skill)
 if st and st<=text_tokens:return True
 low=skill.lower()
 return any(tokens(alias)<=text_tokens for canonical,aliases in SYNONYMS.items() if low==canonical or low in aliases for alias in aliases)

def role_families(text:str)->set[str]:
 low=normalize(text)
 return {family for family,phrases in ROLE_FAMILIES.items() if any(normalize(p) in low for p in phrases)}

def compatible_role(targets:list[str],title:str)->tuple[float,str|None]:
 target_families=set().union(*(role_families(x) for x in targets)) if targets else set()
 job_families=role_families(title)
 if not target_families or not job_families:
  overlap=max((len(tokens(t)&tokens(title))/max(1,len(tokens(t))) for t in targets),default=0)
  return min(1,overlap),None if overlap>=.25 else "Job family could not be confirmed from the title"
 if target_families&job_families:return 1.0,None
 if any(j in RELATED.get(t,set()) for t in target_families for j in job_families):return .55,None
 return 0.0,f"Unrelated role family: {', '.join(sorted(job_families))}"

def required_years(description:str)->tuple[float|None,float|None]:
 text=description.lower();ranges=re.findall(r"(\d{1,2}(?:\.\d)?)\s*(?:-|–|to)\s*(\d{1,2}(?:\.\d)?)\s*(?:years?|yrs?)",text)
 if ranges:
  low,high=ranges[0];return float(low),float(high)
 values=[float(x) for x in re.findall(r"(?:minimum|min\.?|at least|requires?|having)?\s*(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)",text)]
 return (min(values),None) if values else (None,None)

def seniority_level(text:str,default:int=2)->int:
 return max((value for word,value in SENIORITY.items() if re.search(rf"\b{re.escape(word)}\b",text.lower())),default=default)

def candidate_level(years:float)->int:
 return 1 if years<3 else 2 if years<5 else 3 if years<8 else 4

def qualification_sections(description:str)->tuple[str,str]:
 parts=re.split(r"\b(preferred qualifications?|nice to have|bonus|desirable|good to have)\b",description,maxsplit=1,flags=re.I)
 return parts[0]," ".join(parts[1:]) if len(parts)>1 else ""

def match_job(profile:dict,job:dict)->dict:
 title=job.get("title") or "";description=job.get("description") or "";body=tokens(f"{title} {description}");blockers=[];warnings=[]
 targets=[x for x in profile.get("target_titles",[]) if x];title_ratio,title_problem=compatible_role(targets,title)
 if title_problem and title_ratio==0:blockers.append(title_problem)
 elif title_problem:warnings.append(title_problem)
 excluded=[x.lower() for x in profile.get("excluded_roles",[]) if x];excluded_types=[x.lower() for x in profile.get("excluded_employment_types",[]) if x]
 if any(normalize(x) in normalize(title) for x in excluded):blockers.append("Role belongs to an excluded category")
 employment=(job.get("employment_type") or "").lower()
 if any(x in employment for x in excluded_types):blockers.append("Employment type is excluded")

 locations=[x.lower() for x in profile.get("locations",[]) if x and x.lower()!="remote"];job_location=(job.get("location") or "").lower();snippet=description[:1500].lower()
 direct=not job_location or any(x in job_location for x in locations)
 remote_flag=any(x in job_location for x in ("remote","work from home","distributed")) or (not job_location and any(x in snippet for x in ("remote","work from home")))
 remote_countries=[x.lower() for x in profile.get("remote_countries",[]) if x]
 country_hit=any(x in f"{job_location} {snippet}" for x in remote_countries)
 global_remote=any(x in f"{job_location} {snippet}" for x in REMOTE_GLOBAL)
 restricted_elsewhere=(any(h in f"{job_location} {snippet}" for h in ("us only","usa only","united states only","uk only","united kingdom only","canada only","europe only","eu only","germany only","australia only","us citizens","u.s. citizens","must be located in the us","based in the us","based in the uk","rights to work in the us","rights to work in the uk")) and not country_hit)
 remote_eligible=bool(profile.get("remote_allowed")) and not restricted_elsewhere
 if job_location and not direct and not (remote_flag and remote_eligible):blockers.append(f"Location outside preferences: {job.get('location','Unknown')}")
 if re.search(r"\b(us citizens? only|must be a us citizen|security clearance|required clearance)\b",description,re.I):blockers.append("Work-authorization or clearance restriction detected")
 if profile.get("needs_sponsorship") and re.search(r"\b(no|not)\s+(visa\s+)?sponsorship\b",description,re.I):blockers.append("Employer explicitly states sponsorship is unavailable")

 years=float(profile.get("relevant_experience") or profile.get("years_experience") or 0);years_known=years>0
 minimum_years,maximum_years=required_years(description)
 if years_known and minimum_years is not None and years+.25<minimum_years:
  gap=f"Requires about {minimum_years:g} years; verified profile states {years:g}";blockers.append(gap);warnings.append(gap)
 elif minimum_years is not None and not years_known:
  warnings.append(f"Add your years of experience in Career Profile to check the {minimum_years:g}-year requirement")
 title_level=seniority_level(title);person_level=candidate_level(years if years_known else 3)
 if years_known and title_level>=person_level+2:blockers.append("Seniority is substantially above verified relevant experience")
 elif title_level==person_level+1:warnings.append("Role is one seniority step above the current experience band")

 skills=[s for s in profile.get("skills",[]) if s];required_text,preferred_text=qualification_sections(description);req_tokens=tokens(required_text);pref_tokens=tokens(preferred_text)
 matched=[s for s in skills if skill_present(s,body)];required_matches=[s for s in matched if skill_present(s,req_tokens)];preferred_matches=[s for s in matched if skill_present(s,pref_tokens)]
 missing=[s for s in skills if s not in matched];explicit_requirements=[s for s in SYNONYMS if skill_present(s,req_tokens)];profile_tokens=tokens(" ".join(skills))
 missing_mandatory=[s for s in explicit_requirements if not skill_present(s,profile_tokens)]
 if len(missing_mandatory)>=3:blockers.append("Multiple explicit mandatory skill requirements are unverified")
 elif missing_mandatory:warnings.append("Missing mandatory signals: "+", ".join(missing_mandatory[:6]))

 skill_score=len(matched)/max(1,len(skills)) if skills else .2;location_score=1 if direct or remote_eligible else 0
 experience_score=1 if minimum_years is None else (min(1,years/max(1,minimum_years)) if years_known else .6);seniority_score=1 if title_level<=person_level else .55 if title_level==person_level+1 else 0
 evidence_score=min(1,float(profile.get("verified_evidence_ratio") or 0));mandatory_score=1 if not explicit_requirements else (len(explicit_requirements)-len(missing_mandatory))/len(explicit_requirements)
 components={"title":round(title_ratio*100,1),"skills":round(skill_score*100,1),"mandatory":round(mandatory_score*100,1),"location":round(location_score*100,1),"experience":round(experience_score*100,1),"seniority":round(seniority_score*100,1),"evidence":round(evidence_score*100,1)}
 score=round(.30*components["title"]+.20*components["skills"]+.15*components["mandatory"]+.12*components["location"]+.10*components["experience"]+.08*components["seniority"]+.05*components["evidence"],1)
 if title_ratio<.5:score=min(score,54)
 if blockers:score=min(score,35)
 qualified=float(profile.get("qualified_score") or 70);review=float(profile.get("review_score") or 55)
 classification="ineligible" if blockers else "qualified" if score>=qualified else "review" if score>=review else "low_match"
 reasons=[f"Role-family/title compatibility: {components['title']:g}%",f"{len(required_matches)} required-section profile skills matched",f"{len(preferred_matches)} preferred-section profile skills matched","Location and remote eligibility passed" if location_score else "Location eligibility failed"]
 if minimum_years is not None:reasons.append(f"Experience requirement detected: {minimum_years:g}"+(f"–{maximum_years:g} years" if maximum_years else "+ years"))
 if missing:warnings.append(f"Unconfirmed profile skills: {', '.join(missing[:6])}")
 return {"score":score,"classification":classification,"components":components,"blockers":blockers,"matched_skills":matched,"missing_skills":missing_mandatory or missing[:15],"reasons":reasons,"warnings":warnings,"excluded":bool(blockers),"matcher_version":VERSION}
