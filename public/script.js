(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) =>
    Array.from((root || document).querySelectorAll(sel));

  /* Footer year */
  const yearEl = $("#year");
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());

  /* Mobile nav */
  const toggle = $("#navToggle");
  const links = $("#navLinks");
  if (toggle && links) {
    toggle.addEventListener("click", () => {
      const open = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", (e) => {
      if (e.target && e.target.tagName === "A") {
        links.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* Smooth scroll with nav offset */
  $$('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const href = a.getAttribute("href");
      if (!href || href === "#" || href.length < 2) return;
      const target = document.getElementById(href.slice(1));
      if (!target) return;
      e.preventDefault();
      const nav = $("#nav");
      const offset = nav ? nav.offsetHeight + 12 : 0;
      const top =
        target.getBoundingClientRect().top + window.pageYOffset - offset;
      window.scrollTo({ top, behavior: "smooth" });
    });
  });

  /* Reveal on scroll */
  const revealEls = $$(".reveal");
  if ("IntersectionObserver" in window && revealEls.length) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -30px 0px" }
    );
    revealEls.forEach((el) => io.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add("is-visible"));
  }

  /* Nav shadow on scroll */
  const nav = $("#nav");
  if (nav) {
    const onScroll = () => {
      nav.style.boxShadow =
        window.scrollY > 4
          ? "0 8px 24px rgba(0,0,0,.3)"
          : "none";
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* -------- Terminal Demo -------- */
  const DEMOS = [
    {
      cmd: "create file desktop/notes.txt",
      output:
        '<span class="ok">&#10003;</span> File created: C:\\Users\\You\\Desktop\\notes.txt',
    },
    {
      cmd: "check system health",
      output:
        '<span class="ok">&#10003;</span> System Health:\n' +
        "   python : Python 3.14.0\n" +
        "   git    : git version 2.51.1\n" +
        "   node   : v22.22.0\n" +
        "   npm    : 11.6.1",
    },
    {
      cmd: "run command git --version",
      output: '<span class="ok">&#10003;</span> git version 2.51.1',
    },
    {
      cmd: "create project my-app --stack react",
      output:
        '<span class="ok">&#10003;</span> React project \'my-app\' created at C:\\Users\\You\\Desktop\\my-app\n' +
        "   \u2514\u2500 public/ src/App.jsx src/index.jsx package.json .gitignore",
    },
  ];

  const typeTarget = $("#typeTarget");
  const typeCursor = $("#typeCursor");
  const demoOutput = $("#demoOutput");
  const demoBtns = $$("#demoCommands button");
  let activeIdx = 0;
  let typing = false;

  function typeText(text, el, speed) {
    return new Promise((resolve) => {
      let i = 0;
      el.textContent = "";
      const interval = setInterval(() => {
        el.textContent += text[i];
        i++;
        if (i >= text.length) {
          clearInterval(interval);
          resolve();
        }
      }, speed);
    });
  }

  function showOutput(html) {
    demoOutput.innerHTML = "";
    const pre = document.createElement("pre");
    pre.style.margin = "0";
    pre.style.fontFamily = "inherit";
    pre.style.fontSize = "inherit";
    pre.style.whiteSpace = "pre-wrap";
    pre.innerHTML = html;
    pre.style.opacity = "0";
    pre.style.transform = "translateY(6px)";
    demoOutput.appendChild(pre);
    requestAnimationFrame(() => {
      pre.style.transition = "opacity .3s, transform .3s";
      pre.style.opacity = "1";
      pre.style.transform = "none";
    });
  }

  async function runDemo(idx) {
    if (typing) return;
    typing = true;
    activeIdx = idx;

    demoBtns.forEach((b, i) => {
      b.classList.toggle("active", i === idx);
    });

    demoOutput.innerHTML = "";
    if (typeCursor) typeCursor.style.display = "inline";

    await typeText(DEMOS[idx].cmd, typeTarget, 35);

    await new Promise((r) => setTimeout(r, 400));

    if (typeCursor) typeCursor.style.display = "none";
    showOutput(DEMOS[idx].output);

    typing = false;
  }

  if (typeTarget && demoBtns.length) {
    demoBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.getAttribute("data-idx"), 10);
        if (!isNaN(idx)) runDemo(idx);
      });
    });

    runDemo(0);

    setInterval(() => {
      if (typing) return;
      const next = (activeIdx + 1) % DEMOS.length;
      runDemo(next);
    }, 5000);
  }
})();
