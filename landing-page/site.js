/* Simulation Labs — light progressive enhancement. No per-frame/per-char work:
   scroll reveals, a resting behavioral-agent cursor, contents rail, scroll-spy,
   copy buttons, apply form. Reduced-motion safe. */
(function () {
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function slug(s) {
    return (s || "sec").toLowerCase().trim()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "sec";
  }

  /* scroll-spy: highlight the link whose section is in view */
  function scrollspy(links, targets) {
    links = Array.prototype.slice.call(links);
    if (!("IntersectionObserver" in window) || !links.length) return;
    var map = {};
    links.forEach(function (a) {
      var id = (a.getAttribute("href") || "").slice(1);
      if (id) map[id] = a;
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        links.forEach(function (a) { a.classList.remove("active"); });
        var a = map[e.target.id];
        if (a) a.classList.add("active");
      });
    }, { rootMargin: "-88px 0px -62% 0px", threshold: 0 });
    (targets || []).forEach(function (t) { if (t && t.id) io.observe(t); });
  }

  /* Build a "Contents" rail from a prose/note page's <h2>s (deep pages only). */
  function buildEditorial() {
    var main = document.querySelector("main.page");
    if (!main) return;
    var root = main.firstElementChild;
    if (!root || root.classList.contains("docs")) return;
    var scope = root.querySelector(".prose") || root;
    var hs = Array.prototype.slice.call(scope.querySelectorAll("h2"));
    if (hs.length < 2) return;
    var ul = document.createElement("ul");
    hs.forEach(function (h) {
      if (!h.id) h.id = slug(h.textContent);
      var a = document.createElement("a");
      a.href = "#" + h.id;
      a.textContent = h.textContent.replace(/^\s*\d+(\.\d+)?\s+/, "").trim();
      var li = document.createElement("li");
      li.appendChild(a);
      ul.appendChild(li);
    });
    var rail = document.createElement("aside");
    rail.className = "toc-rail";
    var nav = document.createElement("nav");
    nav.className = "toc";
    nav.setAttribute("aria-label", "Contents");
    var label = document.createElement("p");
    label.className = "toc__label";
    label.textContent = "Contents";
    nav.appendChild(label);
    nav.appendChild(ul);
    rail.appendChild(nav);
    var grid = document.createElement("div");
    grid.className = "editorial";
    var body = document.createElement("div");
    body.className = "editorial__body";
    main.insertBefore(grid, root);
    body.appendChild(root);
    grid.appendChild(rail);
    grid.appendChild(body);
    scrollspy(ul.querySelectorAll("a"), hs);
  }

  /* Research/notes: lay publication entries across the width (deep pages). */
  function gridPubs() {
    var wrap = document.querySelector("main.page .wrap");
    if (!wrap) return;
    var pubs = Array.prototype.slice.call(wrap.children).filter(function (el) {
      return el.classList && el.classList.contains("pub");
    });
    if (pubs.length < 2) return;
    wrap.classList.add("wide");
    var grid = document.createElement("div");
    grid.className = "pub-grid";
    wrap.insertBefore(grid, pubs[0]);
    pubs.forEach(function (p) { grid.appendChild(p); });
  }

  /* Docs: scroll-spy the sidebar. */
  function docsSpy() {
    var side = document.querySelector(".docs__side");
    if (!side) return;
    var links = side.querySelectorAll('a[href^="#"]');
    var targets = [];
    links.forEach(function (a) {
      var t = document.getElementById((a.getAttribute("href") || "").slice(1));
      if (t) targets.push(t);
    });
    scrollspy(links, targets);
  }

  /* Copy buttons on code blocks (deep pages). */
  function copyButtons() {
    if (!navigator.clipboard) return;
    document.querySelectorAll("pre").forEach(function (pre) {
      var code = pre.querySelector("code") || pre;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-btn";
      btn.textContent = "Copy";
      btn.addEventListener("click", function () {
        navigator.clipboard.writeText(code.textContent).then(function () {
          btn.textContent = "Copied";
          btn.classList.add("copied");
          setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 1400);
        });
      });
      pre.appendChild(btn);
    });
  }

  /* Smooth in-page scrolling for anchor links. */
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    var id = a.getAttribute("href");
    if (!id || id.length < 2) return;
    var el = document.querySelector(id);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    if (history.replaceState) history.replaceState(null, "", id);
  });

  /* Single-page top-nav scroll-spy. */
  function navSpy() {
    var nav = document.querySelector(".masthead .nav");
    if (!nav) return;
    var links = nav.querySelectorAll('a[href^="#"]');
    if (!links.length) return;
    var targets = [];
    links.forEach(function (a) {
      var t = document.getElementById((a.getAttribute("href") || "").slice(1));
      if (t) targets.push(t);
    });
    scrollspy(links, targets);
  }

  /* Design-partner application form -> mailto. */
  function applyForm() {
    var form = document.getElementById("applyForm");
    if (!form) return;
    var status = document.getElementById("applyStatus");
    var re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var d = new FormData(form);
      function v(k) { return String(d.get(k) || "").trim(); }
      var name = v("name"), company = v("company"), email = v("email"), flow = v("flow");
      if (!re.test(email)) {
        status.hidden = false;
        status.className = "apply-status err";
        status.textContent = "Please enter a valid work email so we can reach you.";
        var el = form.querySelector('[name="email"]');
        if (el) el.focus();
        return;
      }
      var subject = "Design partner application — " + (company || name || email);
      var body = "Name: " + name + "\nCompany: " + company +
        "\nWork email: " + email + "\nFlow to test: " + flow + "\n";
      window.location.href = "mailto:satyam@agentmade.ai?subject=" +
        encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
      status.hidden = false;
      status.className = "apply-status ok";
      status.textContent = "Thanks — we'll be in touch about your flow shortly.";
    });
  }

  /* Scroll-reveal: fade elements up as they enter (CSS transition, one-shot). */
  function reveals() {
    if (!("IntersectionObserver" in window)) return;
    if (reduce) return;
    var els = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
    if (!els.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    els.forEach(function (e) { io.observe(e); });
  }

  /* Hero: the behavioral agent's cursor glides in and rests on the CTA, tapping
     gently every few seconds. Pure CSS transforms — no per-frame work. */
  function heroCursor() {
    var cursor = document.getElementById("agentCursor"),
        btn = document.getElementById("ctaBtn");
    if (!cursor || !btn) return;
    if (reduce) { cursor.style.display = "none"; return; }
    var wrap = btn.parentElement;
    function rest() {
      var w = wrap.getBoundingClientRect(), b = btn.getBoundingClientRect();
      var x = b.left - w.left + b.width * 0.6, y = b.top - w.top + b.height * 0.5 - 2;
      cursor.style.transition = "transform 1.1s cubic-bezier(.33,.66,.24,1)";
      cursor.style.transform = "translate(" + x + "px," + y + "px)";
    }
    cursor.style.transform = "translate(-12px,-6px)";
    setTimeout(rest, 650);
    setInterval(function () {
      cursor.classList.add("is-click");
      var r = document.createElement("span");
      r.className = "cta-ripple";
      btn.appendChild(r);
      setTimeout(function () { cursor.classList.remove("is-click"); }, 170);
      setTimeout(function () { if (r.parentNode) r.parentNode.removeChild(r); }, 640);
    }, 3600);
    window.addEventListener("resize", rest);
  }

  /* Human / Agent reading-mode toggle. Agent view = the same site encoded for
     machine reading (terse, structured, high-density; the llms.txt convention). */
  function viewToggle() {
    var btns = Array.prototype.slice.call(document.querySelectorAll(".vt-btn"));
    if (!btns.length) return;
    function set(v) {
      document.body.classList.toggle("view-agent", v === "agent");
      btns.forEach(function (b) {
        var on = b.getAttribute("data-view") === v;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    }
    btns.forEach(function (b) {
      b.addEventListener("click", function () { set(b.getAttribute("data-view")); });
    });
  }

  /* The agent guides you through the page: a side rail marks its reading position,
     and "walk me through" auto-scrolls section to section. Lightweight. */
  function guide() {
    var secs = Array.prototype.slice.call(document.querySelectorAll("main > section[data-tour]"));
    if (secs.length < 2) return;
    var rail = document.createElement("nav");
    rail.className = "guide";
    rail.setAttribute("aria-label", "Page guide");
    var dots = [];
    secs.forEach(function (s, i) {
      var a = document.createElement("a");
      a.href = "#" + s.id;
      a.className = "guide__dot";
      a.innerHTML = '<span class="guide__label">' + (s.getAttribute("data-tour") || ("Section " + (i + 1))) + '</span><i></i>';
      rail.appendChild(a);
      dots.push(a);
    });
    document.body.appendChild(rail);
    var narr = document.createElement("div");
    narr.className = "agentnarr";
    narr.setAttribute("aria-hidden", "true");
    narr.innerHTML = '<span class="agentnarr__dot"></span><span class="agentnarr__lbl">behavioral agent</span><span class="agentnarr__txt"></span>';
    document.body.appendChild(narr);
    var narrTxt = narr.querySelector(".agentnarr__txt");
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (ents) {
        ents.forEach(function (e) {
          if (!e.isIntersecting) return;
          dots.forEach(function (d) { d.classList.toggle("is-on", d.getAttribute("href") === "#" + e.target.id); });
          var note = e.target.getAttribute("data-tour");
          if (note) { narrTxt.textContent = "reading: " + note; narr.classList.add("show"); }
        });
      }, { rootMargin: "-45% 0px -45% 0px", threshold: 0 });
      secs.forEach(function (s) { io.observe(s); });
    }
    var tourBtn = document.getElementById("tourBtn"), touring = false, ti = 0, timer;
    function stop() {
      touring = false; clearTimeout(timer); rail.classList.remove("touring");
      if (tourBtn) tourBtn.textContent = "Let the agent walk you through";
    }
    function step() {
      if (!touring) return;
      if (ti >= secs.length) { stop(); return; }
      secs[ti].scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      ti++;
      timer = setTimeout(step, 2600);
    }
    if (tourBtn) {
      tourBtn.addEventListener("click", function () {
        if (touring) { stop(); return; }
        touring = true; ti = 0; rail.classList.add("touring"); tourBtn.textContent = "Stop the tour";
        step();
      });
    }
    ["wheel", "touchmove"].forEach(function (ev) {
      window.addEventListener(ev, function () { if (touring) stop(); }, { passive: true });
    });
  }

  buildEditorial();
  gridPubs();
  docsSpy();
  copyButtons();
  navSpy();
  applyForm();
  reveals();
  heroCursor();
  viewToggle();
  guide();
})();
