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

  /* Founding-audit lead form -> FormSubmit (capture + auto-reply) -> Cal booking. */
  var CAL_URL = "https://cal.com/satyamdave-simulation/30min";
  var LEAD_ENDPOINT = "https://formsubmit.co/ajax/sdaveofficial@gmail.com";

  function applyForm() {
    var form = document.getElementById("applyForm");
    if (!form) return;
    var status = document.getElementById("applyStatus");
    var re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    function say(cls, html) {
      status.hidden = false;
      status.className = "apply-status" + (cls ? " " + cls : "");
      status.innerHTML = html;
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var d = new FormData(form);
      function v(k) { return String(d.get(k) || "").trim(); }
      // Honeypot: real users never fill this hidden field.
      if (v("_honey")) return;
      var name = v("name"), company = v("company"), email = v("email"), flow = v("flow");
      if (!re.test(email)) {
        say("err", "Please enter a valid work email so we can reach you.");
        var el = form.querySelector('[name="email"]');
        if (el) el.focus();
        return;
      }
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = true; btn.textContent = "Sending…"; }
      say("", "Sending your request…");

      var payload = {
        name: name, company: company, email: email, flow: flow,
        _subject: "New founding-audit request — " + (company || name || email),
        _template: "table",
        _captcha: "false",
        _autoresponse:
          "Thanks for requesting a Simulation Labs founding audit.\n\n" +
          "We run a swarm of browser agents through one of your flows" +
          (flow ? " (you mentioned: " + flow + ")" : "") +
          " and hand back a report showing the exact pixel where each user segment gives up — in about a week.\n\n" +
          "Fastest next step — grab a 30-min slot so we can scope it:\n" + CAL_URL +
          "\n\n— Simulation Labs"
      };

      fetch(LEAD_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload)
      })
        .then(function (r) {
          return r.json().catch(function () { return {}; })
            .then(function (j) { return { ok: r.ok, j: j }; });
        })
        .then(function (res) {
          if (!res.ok || (res.j && res.j.success === "false")) throw new Error("submit failed");
          var rows = form.querySelectorAll(".row");
          for (var i = 0; i < rows.length; i++) rows[i].style.display = "none";
          if (btn) btn.style.display = "none";
          say("ok",
            "Request received — we'll email you shortly.<br>Fastest path: " +
            "<a class=\"apply-cal\" href=\"" + CAL_URL + "\" target=\"_blank\" rel=\"noopener\">" +
            "grab a 30-min slot →</a>");
        })
        .catch(function () {
          if (btn) { btn.disabled = false; btn.textContent = "Request a seat"; }
          say("err",
            "Couldn't send that just now. Email <a href=\"mailto:sdaveofficial@gmail.com\">" +
            "sdaveofficial@gmail.com</a> or " +
            "<a href=\"" + CAL_URL + "\" target=\"_blank\" rel=\"noopener\">book a call directly →</a>.");
        });
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
    rail.className = "guide at-hero";
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
          var id = e.target.id, isHero = (id === "hero");
          dots.forEach(function (d) { d.classList.toggle("is-on", d.getAttribute("href") === "#" + id); });
          rail.classList.toggle("at-hero", isHero);      // keep the hero screen calm
          var note = e.target.getAttribute("data-tour");
          if (isHero || !note) { narr.classList.remove("show"); }
          else { narrTxt.textContent = "reading: " + note; narr.classList.add("show"); }
        });
      }, { rootMargin: "-45% 0px -45% 0px", threshold: 0 });
      secs.forEach(function (s) { io.observe(s); });
    }
  }

  /* Agent-led guided tour: spotlight each section, point the agent cursor at the key
     element, narrate it in a tooltip. Progress + Back/Next/Esc, pause-on-hover auto-
     advance. rAF runs only while the tour is open (keeps the spotlight glued on scroll). */
  function agentTour() {
    var tourBtn = document.getElementById("tourBtn");
    if (!tourBtn) return;
    var STEPS = [
      { sec: "hero",     focus: ".saydo",       title: "What we do",     line: "We simulate what users do, not what they say. A swarm of browser agents runs your real flow." },
      { sec: "why",      focus: ".big__num",    title: "The problem",    line: "Prompted personas match real users only 11.86% of the time. A stated preference is not a click." },
      { sec: "product",  focus: ".v-do",        title: "Say vs. do",     line: "Same persona. It says the checkout was clean. It actually missed Pay twice and abandoned." },
      { sec: "icp",      focus: ".icp__lead h2",title: "Your ICP",       line: "Every browser agent is driven by a behavioral model custom-fit to your real segments." },
      { sec: "receipts", focus: ".heat",        title: "The receipts",   line: "You get the exact pixel. Here, agents cluster and die on the Pay button." },
      { sec: "research", focus: ".chart",       title: "Measured limits",line: "A 14px tremor misses a 24px target 60.9% of the time. Real, reproducible numbers." },
      { sec: "triggers", focus: ".is-primary",  title: "Where to start", line: "Start by gating every deploy in CI. On-demand audits and an MCP skill expand from there." },
      { sec: "apply",    focus: ".dp2__card",   title: "Ten seats",      line: "We take ten partners a cohort, first come. When the tenth seat is gone, we close. Request yours before it does." }
    ];
    var ov, spot, cur, tip, bar, nextBtn, i = 0, on = false, raf = 0, timers = [], curEl = null, READ = 3400;

    function mk(cls) { var d = document.createElement("div"); d.className = cls; return d; }
    function at(fn, ms) { var t = setTimeout(fn, ms); timers.push(t); return t; }
    function clearTimers() { timers.forEach(clearTimeout); timers = []; }
    function build() {
      ov = mk("tour-ov");
      spot = mk("tour-spot");
      cur = mk("tour-cur");
      cur.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M3.5 2 L3.5 16.8 L7.2 13.4 L9.9 19.9 L12.3 18.9 L9.7 12.6 L14.6 12.6 Z"/></svg><span>behavioral agent</span>';
      tip = mk("tour-tip");
      tip.innerHTML = '<div class="tt-bar"><i></i></div><div class="tt-head"><span class="tt-k"></span>' +
        '<button class="tt-x" type="button" aria-label="Exit tour">esc to exit</button></div>' +
        '<h4 class="tt-title"></h4><p class="tt-line"></p>' +
        '<div class="tt-ctl"><span class="tt-hint">agent is driving</span>' +
        '<button class="tt-next" type="button">Next</button></div>';
      [ov, spot, cur, tip].forEach(function (n) { document.body.appendChild(n); });
      bar = tip.querySelector(".tt-bar i");
      nextBtn = tip.querySelector(".tt-next");
      tip.querySelector(".tt-x").addEventListener("click", stop);
      // Agent drives on a timer, but a human can take over: clicking Next cancels the
      // pending auto-advance and steps immediately (no double-advance).
      nextBtn.addEventListener("click", function () { if (!on) return; clearTimers(); next(); });
    }
    function focusEl(step) { var s = document.getElementById(step.sec); return s ? (s.querySelector(step.focus) || s) : null; }
    function render() {
      if (!on) return;
      var fe = focusEl(STEPS[i]);
      if (fe) {
        var r = fe.getBoundingClientRect(), pad = 8;
        var x = Math.max(6, r.left - pad), y = Math.max(6, r.top - pad),
            w = Math.min(window.innerWidth - 12, r.width + pad * 2), h = r.height + pad * 2;
        spot.style.cssText = "left:" + x + "px;top:" + y + "px;width:" + w + "px;height:" + h + "px";
        var th = tip.offsetHeight || 170, room = window.innerHeight - (y + h) - 20;
        var top = room > th ? (y + h + 14) : Math.max(12, y - 14 - th);
        tip.style.left = Math.min(Math.max(12, x), window.innerWidth - Math.min(352, window.innerWidth - 12)) + "px";
        tip.style.top = top + "px";
        // agent cursor: rests on the focused element, then travels to the Next button
        var ce = (curEl === nextBtn) ? nextBtn : fe, cr = ce.getBoundingClientRect();
        // On the Next button the cursor's tip lands on the button (anchor offset by the arrow
        // tip's ~6/4 origin) so the press reads as a real click; the cursor sits above the
        // tooltip in z-order (see .tour-cur z-index) so it's never hidden behind the button.
        var cx = (ce === nextBtn) ? (cr.left + cr.width * 0.5 - 6) : (cr.right - 6);
        var cy = (ce === nextBtn) ? (cr.top + cr.height * 0.5 - 4) : (cr.bottom - 4);
        cur.style.transform = "translate(" + cx + "px," + cy + "px)";
      }
      raf = requestAnimationFrame(render);
    }
    function tap(onNext, cb) {
      cur.classList.add("is-click");
      if (onNext) nextBtn.classList.add("flash"); else spot.classList.add("hit");
      at(function () { cur.classList.remove("is-click"); nextBtn.classList.remove("flash"); spot.classList.remove("hit"); if (cb) cb(); }, 210);
    }
    function show() {
      clearTimers();
      var step = STEPS[i], fe = focusEl(step);
      tip.querySelector(".tt-k").textContent = (i + 1) + " / " + STEPS.length;
      tip.querySelector(".tt-title").textContent = step.title;
      tip.querySelector(".tt-line").textContent = step.line;
      nextBtn.textContent = (i === STEPS.length - 1) ? "Finish" : "Next";
      curEl = fe;
      if (fe) fe.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      if (reduce) { at(next, 2400); return; }
      // 1) the agent clicks the highlighted element
      at(function () { tap(false); }, 780);
      at(function () { tap(false); }, 1280);
      // progress bar counts down the read time
      bar.style.transition = "none"; bar.style.width = "0%"; void bar.offsetWidth;
      bar.style.transition = "width " + READ + "ms linear"; bar.style.width = "100%";
      // 2) the agent moves its cursor to Next and clicks it -> advance
      at(function () { curEl = nextBtn; }, READ);
      at(function () { tap(true, next); }, READ + 640);
    }
    function next() { if (i < STEPS.length - 1) { i++; show(); } else { stop(); var a = document.getElementById("apply"); if (a) a.scrollIntoView({ behavior: reduce ? "auto" : "smooth" }); } }
    function onKey(e) { if (e.key === "Escape") stop(); }
    function block(e) { e.preventDefault(); }
    function blockKeys(e) {
      if (e.key === "Escape") return;
      if ([" ", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", "Spacebar"].indexOf(e.key) >= 0) e.preventDefault();
    }
    function start() {
      if (on) { stop(); return; }
      if (!ov) build();
      on = true; i = 0;
      document.body.classList.add("tour-on");
      tourBtn.textContent = "End tour";
      window.addEventListener("wheel", block, { passive: false });
      window.addEventListener("touchmove", block, { passive: false });
      window.addEventListener("keydown", blockKeys, false);
      document.addEventListener("keydown", onKey);
      show(); render();
    }
    function stop() {
      on = false; clearTimers(); if (raf) cancelAnimationFrame(raf); raf = 0; curEl = null;
      document.body.classList.remove("tour-on");
      tourBtn.textContent = "Let the agent walk you through";
      window.removeEventListener("wheel", block);
      window.removeEventListener("touchmove", block);
      window.removeEventListener("keydown", blockKeys);
      document.removeEventListener("keydown", onKey);
    }
    tourBtn.addEventListener("click", start);
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
  agentTour();
})();
