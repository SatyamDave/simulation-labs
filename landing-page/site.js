/* Simulation Labs — small progressive enhancements: contents rail, scroll-spy,
   publication grid, copy-code buttons, smooth in-page scroll. Reduced-motion safe. */
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

  /* Build a "Contents" rail from a prose/note page's <h2>s and go two-column. */
  function buildEditorial() {
    var main = document.querySelector("main.page");
    if (!main) return;
    var root = main.firstElementChild;
    if (!root || root.classList.contains("docs")) return; // docs has its own rail

    var scope = root.querySelector(".prose") ||
      (root.classList.contains("note") ? root : root);
    var hs = Array.prototype.slice.call(scope.querySelectorAll("h2"));
    if (hs.length < 2) return; // home/research: no TOC

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

  /* Home/Research: lay the publication entries out across the full width. */
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

  /* Docs: scroll-spy the existing sidebar. */
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

  /* Copy buttons on code blocks. */
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
          setTimeout(function () {
            btn.textContent = "Copy";
            btn.classList.remove("copied");
          }, 1400);
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

  /* Scroll-reveal: fade section bodies up as they enter. */
  function reveals() {
    if (!("IntersectionObserver" in window)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var els = Array.prototype.slice.call(document.querySelectorAll(".sect__body"));
    if (!els.length) return;
    els.forEach(function (e) { e.classList.add("reveal"); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
    els.forEach(function (e) { io.observe(e); });
  }

  buildEditorial();
  gridPubs();
  docsSpy();
  copyButtons();
  navSpy();
  applyForm();
  reveals();
})();
