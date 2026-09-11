/* Karna OS landing page interactions */
(function () {
  "use strict";

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- footer year ---------- */
  var year = $("#year");
  if (year) { year.textContent = String(new Date().getFullYear()); }

  /* ---------- mobile nav ---------- */
  var menuBtn = $("#menuBtn");
  var mobileNav = $("#mobileNav");
  if (menuBtn && mobileNav) {
    menuBtn.addEventListener("click", function () {
      var open = mobileNav.hasAttribute("hidden");
      if (open) { mobileNav.removeAttribute("hidden"); } else { mobileNav.setAttribute("hidden", ""); }
      menuBtn.setAttribute("aria-expanded", String(open));
    });
    $$("a", mobileNav).forEach(function (a) {
      a.addEventListener("click", function () {
        mobileNav.setAttribute("hidden", "");
        menuBtn.setAttribute("aria-expanded", "false");
      });
    });
  }

  /* ---------- reveal on scroll ---------- */
  var revealEls = $$(".reveal");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---------- scroll progress bar ---------- */
  var scrollBar = $("#scrollBar");
  function paintScroll() {
    if (!scrollBar) { return; }
    var doc = document.documentElement;
    var max = doc.scrollHeight - window.innerHeight;
    scrollBar.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
  }
  window.addEventListener("scroll", paintScroll, { passive: true });
  paintScroll();

  /* ---------- hero cursor glow ---------- */
  var heroSection = $(".hero");
  var glow = $("#cursorGlow");
  var finePointer = !(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
  if (glow && heroSection && finePointer) {
    heroSection.addEventListener("pointermove", function (e) {
      var r = heroSection.getBoundingClientRect();
      glow.style.left = (e.clientX - r.left) + "px";
      glow.style.top = (e.clientY - r.top) + "px";
    });
  }

  /* ---------- 3D tilt on cards ---------- */
  if (finePointer) {
    $$(".match-panel, .studio-panel, .router-panel, .step, .review").forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var r = card.getBoundingClientRect();
        var rx = ((e.clientY - r.top) / r.height - 0.5) * -6;
        var ry = ((e.clientX - r.left) / r.width - 0.5) * 8;
        card.style.transform = "perspective(900px) rotateX(" + rx.toFixed(2) + "deg) rotateY(" + ry.toFixed(2) + "deg)";
      });
      card.addEventListener("pointerleave", function () { card.style.transform = ""; });
    });
  }

  /* ---------- animated counters ---------- */
  function countUp(el, target, suffix) {
    var start = null, dur = 1400;
    function tick(ts) {
      if (!start) { start = ts; }
      var p = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = String(Math.round(target * eased)) + (suffix || "");
      if (p < 1) { requestAnimationFrame(tick); }
    }
    requestAnimationFrame(tick);
  }
  var statEls = $$("[data-count]");
  if (statEls.length && "IntersectionObserver" in window) {
    var statIo = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          countUp(e.target, parseInt(e.target.getAttribute("data-count"), 10) || 0, e.target.getAttribute("data-suffix"));
          statIo.unobserve(e.target);
        }
      });
    }, { threshold: 0.4 });
    statEls.forEach(function (el) { statIo.observe(el); });
  } else {
    statEls.forEach(function (el) {
      el.textContent = el.getAttribute("data-count") + (el.getAttribute("data-suffix") || "");
    });
  }

  /* ---------- hero: match ticker + counter ---------- */
  var heroJobs = [
    { title: "Senior Backend Engineer", meta: "Northwind · Remote (IN) · posted 6h ago", score: 82, verdict: "qualified", label: "QUALIFIED" },
    { title: "Platform Engineer", meta: "Helios Labs · Bengaluru (Hybrid) · posted 1d ago", score: 74, verdict: "qualified", label: "QUALIFIED" },
    { title: "Data Analyst", meta: "Fintrail · Pune · posted 3h ago", score: 61, verdict: "review", label: "REVIEW" },
    { title: "Engineering Manager", meta: "Corebank · Remote (EU only) · posted 2d ago", score: 28, verdict: "reject", label: "REJECTED" }
  ];
  var heroIdx = 0, heroTotal = 0, heroToday = 0;
  var cardEl = $("#matchCard"), ringEl = $("#matchRing"), scoreEl = $("#matchScore");
  var titleEl = $("#matchTitle"), metaEl = $("#matchMeta"), verdictEl = $("#matchVerdict");
  var totalEl = $("#matchTotal"), todayEl = $("#matchToday");

  /* real numbers from the local database — zero on a fresh install, honest always */
  fetch("/api/stats").then(function (r) { return r.ok ? r.json() : null; }).then(function (s) {
    if (!s) { return; }
    heroTotal = s.matches_scored || 0;
    heroToday = s.jobs_indexed || 0;
    if (totalEl) { totalEl.textContent = String(heroTotal); }
    if (todayEl) { todayEl.textContent = String(heroToday); }
  }).catch(function () { /* keep zeros */ });

  function animateRing(ring, scoreEl, score, verdict) {
    if (!ring) { return; }
    ring.classList.remove("warn", "bad");
    if (verdict === "review") { ring.classList.add("warn"); }
    if (verdict === "reject") { ring.classList.add("bad"); }
    var current = parseInt(ring.getAttribute("data-current") || "0", 10);
    var start = null, dur = 700;
    function tick(ts) {
      if (!start) { start = ts; }
      var p = Math.min(1, (ts - start) / dur);
      var val = Math.round(current + (score - current) * p);
      ring.style.setProperty("--score", String(val));
      if (scoreEl) { scoreEl.textContent = String(val); }
      if (p < 1) { requestAnimationFrame(tick); } else { ring.setAttribute("data-current", String(score)); }
    }
    requestAnimationFrame(tick);
  }

  function showHeroJob(i) {
    var j = heroJobs[i];
    if (!j || !cardEl) { return; }
    cardEl.style.opacity = "0";
    setTimeout(function () {
      if (titleEl) { titleEl.textContent = j.title; }
      if (metaEl) { metaEl.textContent = j.meta; }
      if (verdictEl) {
        verdictEl.className = "verdict " + j.verdict;
        verdictEl.textContent = j.label;
      }
      animateRing(ringEl, scoreEl, j.score, j.verdict);
      cardEl.style.transition = "opacity .25s ease";
      cardEl.style.opacity = "1";
    }, 180);
  }

  if (cardEl) {
    setTimeout(function () { showHeroJob(0); }, 250);
    setInterval(function () {
      heroIdx = (heroIdx + 1) % heroJobs.length;
      showHeroJob(heroIdx);
    }, 3200);
  }

  /* ---------- matching demo: role chips + strict toggle ---------- */
  var profiles = {
    software: {
      name: "Senior Backend Engineer · Northwind",
      loose: 82,
      checks: [
        { text: "Job family: software engineering", pass: true },
        { text: "Seniority: senior (5+ yrs)", pass: true },
        { text: "Mandatory skills: Python, FastAPI, SQL", pass: true },
        { text: "Location: remote matches your time zone", pass: true },
        { text: "Experience: 6 yrs vs 5 required", pass: true },
        { text: "Authorization: no restriction stated", pass: true }
      ]
    },
    data: {
      name: "Data Analyst · Fintrail",
      loose: 61,
      checks: [
        { text: "Job family: adjacent (analyst vs engineering)", pass: false, why: "strict" },
        { text: "Title distance: 2 levels from your target", pass: true },
        { text: "Mandatory skills: SQL, dashboards, Python", pass: true },
        { text: "Location: on-site 3 days — within radius", pass: true },
        { text: "Experience: 4 yrs vs 3 required", pass: true },
        { text: "Salary band overlaps your floor", pass: true }
      ]
    },
    pm: {
      name: "Product Manager · Corebank",
      loose: 44,
      checks: [
        { text: "Job family: management track", pass: false, why: "strict" },
        { text: "Mandatory skills: stakeholder scoping", pass: false, why: "gap" },
        { text: "Title distance: 3 levels from your target", pass: false, why: "gap" },
        { text: "Location: hybrid Bengaluru", pass: true },
        { text: "Experience: 6 yrs vs 5 required", pass: true },
        { text: "Authorization: no restriction stated", pass: true }
      ]
    }
  };

  function renderChecks(list, strict) {
    var ul = $("#panelChecks");
    if (!ul) { return; }
    var visible = strict ? list.checks.filter(function (c) { return c.pass || c.why === "strict"; }) : list.checks;
    ul.innerHTML = visible.map(function (c) {
      var cls = c.pass ? "pass" : "fail";
      var icon = c.pass ? "✓" : "✕";
      return '<li class="' + cls + '"><i>' + icon + '</i><span>' + c.text + "</span></li>";
    }).join("");
    var failedStrict = visible.some(function (c) { return !c.pass && c.why === "strict"; });
    var failedAny = list.checks.some(function (c) { return !c.pass; });
    var ring = $("#panelRing"), scoreEl = $("#panelScore");
    var verdict = $("#panelVerdict"), note = $("#panelNote"), jobEl = $("#panelJob");
    var state;
    if (strict && failedStrict) {
      state = { v: "reject", label: "REJECTED", cls: "bad", note: "Strict gate failed — excluded from your inbox." };
    } else if (strict && failedAny) {
      state = { v: "review", label: "REVIEW", cls: "warn", note: "Passes strict gates — flagged for your judgement." };
    } else if (!strict && failedAny) {
      state = { v: "review", label: "REVIEW", cls: "warn", note: "Partial fit — review the failing checks." };
    } else {
      state = { v: "qualified", label: "QUALIFIED", cls: "", note: "Meets every gate — shortlist it." };
    }
    var score = state.v === "reject" ? Math.max(12, list.loose - 25) : (state.v === "review" ? Math.max(40, list.loose - 12) : list.loose);
    if (jobEl) { jobEl.textContent = list.name; }
    if (verdict) { verdict.className = "verdict " + state.v; verdict.textContent = state.label; }
    if (note) { note.textContent = state.note; }
    animateRing(ring, scoreEl, score, state.v);
  }

  var currentProfile = profiles.software;
  var strictOn = false;
  $$(".demo-controls .chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      $$(".demo-controls .chip").forEach(function (c) { c.classList.remove("on"); });
      chip.classList.add("on");
      currentProfile = profiles[chip.getAttribute("data-role")] || profiles.software;
      renderChecks(currentProfile, strictOn);
    });
  });
  var strictToggle = $("#strictToggle");
  if (strictToggle) {
    strictToggle.addEventListener("change", function () {
      strictOn = strictToggle.checked;
      renderChecks(currentProfile, strictOn);
    });
  }
  renderChecks(currentProfile, false);

  /* ---------- interview studio demo ---------- */
  var answers = {
    "Tell me about a time you led under pressure.":
      "Situation: our payment service degraded during a festival-week traffic spike.\nTask: as senior engineer, I had to restore service while coordinating three teams.\nAction: I triaged by blast radius, rolled back the queue change, and set up a live status channel so stakeholders stopped pinging individuals.\nResult: recovery in 48 minutes, and the incident runbook we wrote is still in use — zero repeat outages in 14 months.",
    "Why do you want this role?":
      "Your team owns the exact intersection I have been building toward: distributed systems with real user impact. In my current role I rebuilt an ingestion pipeline that cut processing time by 60% — the work in your job post is a direct continuation of that, at larger scale, with the mentorship of a platform group I admire.",
    "Describe a conflict with a teammate.":
      "Situation: a teammate and I disagreed on migrating our scheduler to event-driven design.\nTask: we needed one decision before the sprint froze.\nAction: I proposed a two-day spike with agreed success metrics instead of debating opinions. We reviewed data together.\nResult: we chose the event-driven path with his rollback safeguards merged in — and he became the feature's strongest advocate.",
    "What is your biggest professional win?":
      "I turned an undocumented, tribal-knowledge deployment process into a one-command pipeline. Adoption went from 2 to 11 teams in a quarter, release failures dropped 70%, and I ran the enablement sessions myself. It started as a side fix and became the org standard."
  };
  var studioQuestion = $("#studioQuestion"), studioAnswer = $("#studioAnswer");
  var typeTimer = null;
  function typeAnswer(text) {
    if (!studioAnswer) { return; }
    if (typeTimer) { clearInterval(typeTimer); }
    studioAnswer.textContent = "";
    var caret = document.createElement("span");
    caret.className = "caret";
    studioAnswer.appendChild(caret);
    var i = 0;
    typeTimer = setInterval(function () {
      i += 3;
      if (i >= text.length) {
        studioAnswer.textContent = text;
        return;
      }
      studioAnswer.textContent = text.slice(0, i);
      studioAnswer.appendChild(caret);
    }, 16);
  }
  if (studioQuestion && studioAnswer) {
    $$(".q-list .q").forEach(function (btn) {
      btn.addEventListener("click", function () {
        $$(".q-list .q").forEach(function (b) { b.classList.remove("on"); });
        btn.classList.add("on");
        var q = btn.textContent.replace(/^“|”$/g, "");
        if (studioQuestion) { studioQuestion.textContent = "“" + q + "”"; }
        typeAnswer(answers[q] || "");
      });
    });
    var firstQ = $(".q-list .q.on");
    if (firstQ) {
      var q0 = firstQ.textContent.replace(/^“|”$/g, "");
      typeAnswer(answers[q0] || "");
    }
  }

  /* ---------- AI router failover demo ---------- */
  var routerLog = $("#routerLog");
  var chain = $$("#routerChain .provider");
  var routerBtn = $("#routerRun");
  var timers = [];
  function clearTimers() {
    timers.forEach(function (t) { clearTimeout(t); });
    timers = [];
  }
  function setProvider(el, state, label) {
    if (!el) { return; }
    el.setAttribute("data-state", state);
    var b = $(".p-state", el);
    if (b && label) { b.textContent = label; }
  }
  function runRouter() {
    clearTimers();
    chain.forEach(function (el) { setProvider(el, "idle", "idle"); });
    if (routerLog) { routerLog.textContent = "▸ dispatching task: tailor_resume …"; }
    var steps = [
      function () {
        setProvider(chain[0], "active", "trying");
        if (routerLog) { routerLog.textContent += "\n▸ ollama: rate-limited (429) — backing off"; }
      },
      function () {
        setProvider(chain[0], "failed", "failed");
        setProvider(chain[1], "active", "trying");
        if (routerLog) { routerLog.textContent += "\n▸ gemini: streaming draft …"; }
      },
      function () {
        setProvider(chain[1], "done", "done ✓");
        setProvider(chain[2], "skipped", "skipped");
        if (routerLog) { routerLog.textContent += "\n✓ task complete in 2.4s — resume tailored, awaiting your approval"; }
      }
    ];
    steps.forEach(function (fn, i) { timers.push(setTimeout(fn, 700 + i * 950)); });
  }
  if (routerBtn && chain.length) {
    routerBtn.addEventListener("click", runRouter);
  }
  if ("IntersectionObserver" in window && chain.length) {
    var routerIo = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { runRouter(); routerIo.disconnect(); }
      });
    }, { threshold: 0.35 });
    routerIo.observe($("#routerChain"));
  }
})();
