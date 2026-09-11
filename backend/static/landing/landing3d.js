/* Karna OS hero — 3D career scene (Three.js): laptop, graduation cap, clock, briefcase, resume */
(function () {
  "use strict";

  var canvas = document.getElementById("heroCanvas");
  var hero = document.querySelector(".hero");
  if (!canvas || !hero) { return; }

  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function bail() {
    if (canvas && canvas.parentNode) { canvas.parentNode.removeChild(canvas); }
  }

  if (reduced || typeof THREE === "undefined") { bail(); return; }

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
  } catch (err) {
    bail();
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(46, 1, 0.1, 100);
  camera.position.set(0, 0, 15);

  scene.add(new THREE.AmbientLight(0xf2f8ff, 1.05));
  var key = new THREE.DirectionalLight(0xffffff, 0.9); key.position.set(6, 9, 10); scene.add(key);
  var sky = new THREE.PointLight(0x88bdf2, 0.85, 70); sky.position.set(-12, -4, 8); scene.add(sky);
  var warm = new THREE.PointLight(0xbdddfc, 0.7, 70); warm.position.set(12, 5, 6); scene.add(warm);

  var world = new THREE.Group();
  scene.add(world);

  var disposables = [];
  function track(res) { disposables.push(res); return res; }

  var C = { sky: 0x88bdf2, baby: 0xbdddfc, steel: 0x6a89a7, slate: 0x384959, white: 0xffffff, ink: 0x2c3e50 };

  function mat(color, opts) {
    opts = opts || {};
    return track(new THREE.MeshPhysicalMaterial({
      color: color,
      metalness: opts.metal !== undefined ? opts.metal : 0.12,
      roughness: opts.rough !== undefined ? opts.rough : 0.32,
      clearcoat: 0.8, clearcoatRoughness: 0.28,
      transparent: true, opacity: opts.opacity !== undefined ? opts.opacity : 0.97
    }));
  }

  function box(w, h, d, material, r) {
    var geo;
    if (r) {
      var s = new THREE.Shape();
      var x = -w / 2, y = -h / 2;
      s.moveTo(x + r, y);
      s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
      s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
      s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
      geo = track(new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 2, curveSegments: 6 }));
    } else {
      geo = track(new THREE.BoxGeometry(w, h, d));
    }
    return new THREE.Mesh(geo, material);
  }

  function sphere(r, material) {
    return new THREE.Mesh(track(new THREE.SphereGeometry(r, 36, 36)), material);
  }
  function torus(r, t, material) {
    return new THREE.Mesh(track(new THREE.TorusGeometry(r, t, 20, 72)), material);
  }
  function cylinder(rt, rb, h, material) {
    return new THREE.Mesh(track(new THREE.CylinderGeometry(rt, rb, h, 36)), material);
  }

  var items = [];
  function place(obj, x, y, z, bobSpeed, rotSpeed) {
    obj.position.set(x, y, z);
    obj.userData.bob = bobSpeed || 0.6;
    obj.userData.rot = rotSpeed || 0;
    obj.userData.phase = Math.random() * Math.PI * 2;
    obj.userData.baseY = y;
    obj.userData.baseX = x;
    world.add(obj);
    items.push(obj);
    return obj;
  }

  /* Responsive spread: on narrower screens push objects toward the edges and
     shrink them so the headline text always stays readable. */
  function layoutScene() {
    var w = hero.clientWidth, h = hero.clientHeight;
    if (!w || !h) { return; }
    var aspect = w / h;
    var xFactor = Math.max(1, 1.85 / aspect);          /* narrow => further out */
    var s = Math.max(0.52, Math.min(1, aspect / 1.7)); /* narrow => smaller */
    world.scale.set(s, s, s);
    for (var i = 0; i < items.length; i++) {
      items[i].position.x = items[i].userData.baseX * xFactor;
    }
  }

  /* ---------- LAPTOP ---------- */
  (function buildLaptop() {
    var g = new THREE.Group();
    var base = box(4.4, 0.22, 2.9, mat(C.slate), 0.1);
    base.position.y = -0.11;
    g.add(base);
    var keys = box(4.0, 0.06, 2.4, mat(C.ink, { rough: 0.5 }), 0.05);
    keys.position.set(0, 0.05, 0.15);
    g.add(keys);
    var screen = box(4.4, 2.8, 0.16, mat(C.slate), 0.1);
    screen.position.set(0, 1.32, -1.32);
    screen.rotation.x = -0.28;
    g.add(screen);
    var face = box(4.0, 2.44, 0.05, mat(C.sky, { rough: 0.2, opacity: 0.95 }), 0.06);
    face.position.set(0, 1.34, -1.21);
    face.rotation.x = -0.28;
    g.add(face);
    var bar1 = box(2.6, 0.12, 0.03, mat(C.white, { rough: 0.4 })); bar1.position.set(-0.4, 1.95, -1.16); bar1.rotation.x = -0.28; g.add(bar1);
    var bar2 = box(3.2, 0.1, 0.03, mat(C.baby, { rough: 0.4 })); bar2.position.set(-0.1, 1.55, -1.17); bar2.rotation.x = -0.28; g.add(bar2);
    var bar3 = box(2.2, 0.1, 0.03, mat(C.baby, { rough: 0.4 })); bar3.position.set(-0.5, 1.2, -1.18); bar3.rotation.x = -0.28; g.add(bar3);
    g.rotation.y = 0.42;
    place(g, -4.3, -2.6, 0.5, 0.55, 0.05);
  })();

  /* ---------- GRADUATION CAP ---------- */
  (function buildCap() {
    var g = new THREE.Group();
    var head = cylinder(1.15, 1.3, 0.7, mat(C.slate));
    g.add(head);
    var board = box(3.6, 0.16, 3.6, mat(C.ink), 0.08);
    board.position.y = 0.42;
    g.add(board);
    var button = sphere(0.09, mat(C.sky)); button.position.y = 0.55; g.add(button);
    var cord = cylinder(0.035, 0.035, 1.7, mat(C.sky));
    cord.position.set(1.35, 0.0, 1.1);
    cord.rotation.z = 0.9;
    g.add(cord);
    var tassel = sphere(0.16, mat(C.sky)); tassel.position.set(1.72, -0.75, 1.35); g.add(tassel);
    g.rotation.y = -0.5;
    place(g, 4.9, 3.3, -1.6, 0.75, 0.08);
  })();

  /* ---------- CLOCK ---------- */
  var clockGroup;
  (function buildClock() {
    clockGroup = new THREE.Group();
    var rim = torus(1.55, 0.2, mat(C.steel));
    clockGroup.add(rim);
    var faceM = sphere(1.38, mat(C.white, { rough: 0.25 }));
    faceM.scale.z = 0.18;
    clockGroup.add(faceM);
    var marks = box(0.5, 0.08, 0.05, mat(C.slate)); marks.position.set(0, 1.05, 0.3); clockGroup.add(marks);
    var hourHand = box(0.12, 0.7, 0.06, mat(C.slate)); hourHand.position.y = 0.28; hourHand.position.z = 0.32;
    var hourPivot = new THREE.Group(); hourPivot.add(hourHand); hourPivot.rotation.z = -0.9; clockGroup.add(hourPivot);
    var minHand = box(0.1, 1.05, 0.06, mat(C.sky)); minHand.position.y = 0.45; minHand.position.z = 0.34;
    var minPivot = new THREE.Group(); minPivot.add(minHand); minPivot.rotation.z = 0.7; clockGroup.add(minPivot);
    var secPivot = new THREE.Group();
    var secHand = box(0.045, 1.2, 0.04, mat(C.ink)); secHand.position.y = 0.45; secHand.position.z = 0.36;
    secPivot.add(secHand); clockGroup.add(secPivot);
    var center = sphere(0.09, mat(C.ink)); center.position.z = 0.38; clockGroup.add(center);
    clockGroup.userData.sec = secPivot;
    clockGroup.userData.min = minPivot;
    clockGroup.userData.hour = hourPivot;
    place(clockGroup, -4.9, 3.1, -1.4, 0.7, 0.06);
  })();

  /* ---------- BRIEFCASE ---------- */
  (function buildCase() {
    var g = new THREE.Group();
    var body = box(3.3, 2.2, 1.15, mat(C.steel), 0.18);
    g.add(body);
    var lid = box(3.3, 0.55, 1.19, mat(C.slate), 0.16);
    lid.position.y = 0.95;
    g.add(lid);
    var clasp = box(0.5, 0.28, 0.25, mat(C.sky));
    clasp.position.set(0, 0.62, 0.62);
    g.add(clasp);
    var handle = torus(0.62, 0.09, mat(C.ink));
    handle.position.set(0, 1.42, 0);
    handle.rotation.y = Math.PI / 2;
    handle.scale.y = 0.6;
    g.add(handle);
    g.rotation.y = -0.38;
    place(g, 4.7, -3.1, 0.2, 0.6, -0.06);
  })();

  /* ---------- RESUME PAPERS ---------- */
  (function buildResume() {
    var g = new THREE.Group();
    var paper1 = box(2.1, 2.9, 0.07, mat(C.white, { rough: 0.35 }), 0.06);
    paper1.rotation.z = 0.12;
    g.add(paper1);
    var paper2 = box(2.1, 2.9, 0.07, mat(C.baby, { rough: 0.35, opacity: 0.95 }), 0.06);
    paper2.position.set(0.35, -0.12, -0.1);
    paper2.rotation.z = -0.1;
    g.add(paper2);
    var l1 = box(1.4, 0.12, 0.03, mat(C.sky)); l1.position.set(-0.25, 0.95, 0.07); l1.rotation.z = 0.12; g.add(l1);
    var l2 = box(1.55, 0.09, 0.03, mat(C.steel)); l2.position.set(-0.15, 0.55, 0.07); l2.rotation.z = 0.12; g.add(l2);
    var l3 = box(1.3, 0.09, 0.03, mat(C.steel)); l3.position.set(-0.28, 0.25, 0.07); l3.rotation.z = 0.12; g.add(l3);
    var seal = sphere(0.22, mat(C.sky)); seal.position.set(0.45, -0.75, 0.1); g.add(seal);
    g.rotation.y = 0.35;
    place(g, -4.6, -0.4, -0.8, 0.8, 0.07);
  })();

  /* ---------- AMBIENT ORBS ---------- */
  var orbColors = [C.sky, C.baby, C.steel, 0xd9e7f6, 0xcfe3f8];
  var orbs = [];
  for (var i = 0; i < 10; i++) {
    var orb = sphere(0.16 + Math.random() * 0.34, mat(orbColors[i % orbColors.length], { rough: 0.4 }));
    var angle = (i / 10) * Math.PI * 2;
    var radius = 8.5 + Math.random() * 3.5;
    place(orb, Math.cos(angle) * radius, Math.sin(angle) * radius * 0.6, -4.5 - Math.random() * 4.5, 0.5 + Math.random() * 0.4, 0.05);
    orbs.push(orb);
  }

  /* ---------- mouse parallax ---------- */
  var targetX = 0, targetY = 0, curX = 0, curY = 0;
  window.addEventListener("pointermove", function (e) {
    targetX = (e.clientX / window.innerWidth - 0.5) * 2;
    targetY = (e.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });

  function resize() {
    var w = hero.clientWidth, h = hero.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", function () { resize(); layoutScene(); });
  resize();
  layoutScene();

  var visible = true;
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
    }, { threshold: 0.02 }).observe(hero);
  }
  document.addEventListener("visibilitychange", function () { visible = !document.hidden && visible; });

  var clock3 = new THREE.Clock();
  function frame() {
    requestAnimationFrame(frame);
    if (!visible) { return; }
    var t = clock3.getElapsedTime();

    curX += (targetX - curX) * 0.045;
    curY += (targetY - curY) * 0.045;
    world.rotation.y = curX * 0.14;
    world.rotation.x = curY * -0.09;
    world.position.x = curX * 0.6;
    world.position.y = curY * -0.4;

    for (var i = 0; i < items.length; i++) {
      var m = items[i];
      m.position.y = m.userData.baseY + Math.sin(t * m.userData.bob + m.userData.phase) * 0.28;
      if (m.userData.rot) { m.rotation.y += m.userData.rot * 0.004; }
    }
    /* live clock hands — “your time, well spent” */
    if (clockGroup) {
      var now = new Date();
      clockGroup.userData.sec.rotation.z = -(now.getSeconds() + now.getMilliseconds() / 1000) / 60 * Math.PI * 2;
      clockGroup.userData.min.rotation.z = -(now.getMinutes() + now.getSeconds() / 60) / 60 * Math.PI * 2;
      clockGroup.userData.hour.rotation.z = -((now.getHours() % 12) + now.getMinutes() / 60) / 12 * Math.PI * 2;
    }

    renderer.render(scene, camera);
  }
  frame();

  window.addEventListener("beforeunload", function () {
    disposables.forEach(function (d) { if (d && d.dispose) { d.dispose(); } });
    renderer.dispose();
  });
})();
