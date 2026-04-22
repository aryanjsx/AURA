/* AURA — Landing interactivity
   Kept intentionally minimal: mobile nav, scroll reveal, year, smooth anchors. */

(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* Current year in footer */
  const yearEl = $("#year");
  if (yearEl) {
    yearEl.textContent = String(new Date().getFullYear());
  }

  /* Mobile nav toggle */
  const toggle = $("#navToggle");
  const links = $(".nav__links");
  if (toggle && links) {
    toggle.addEventListener("click", () => {
      const isOpen = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    links.addEventListener("click", (e) => {
      const target = e.target;
      if (target && target.tagName === "A") {
        links.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* Smooth scroll for same-page anchors (native smooth + offset) */
  $$('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const href = a.getAttribute("href");
      if (!href || href === "#" || href.length < 2) return;
      const target = document.getElementById(href.slice(1));
      if (!target) return;
      e.preventDefault();
      const nav = $(".nav");
      const offset = nav ? nav.offsetHeight + 8 : 0;
      const top =
        target.getBoundingClientRect().top + window.pageYOffset - offset;
      window.scrollTo({ top, behavior: "smooth" });
    });
  });

  /* Reveal-on-scroll using IntersectionObserver */
  const revealables = $$(".reveal");
  if ("IntersectionObserver" in window && revealables.length) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (entry.isIntersecting) {
            const el = entry.target;
            el.style.transitionDelay = Math.min(i * 40, 200) + "ms";
            el.classList.add("is-visible");
            io.unobserve(el);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );

    revealables.forEach((el) => io.observe(el));
  } else {
    revealables.forEach((el) => el.classList.add("is-visible"));
  }

  /* Subtle nav shadow on scroll */
  const nav = $(".nav");
  if (nav) {
    const onScroll = () => {
      if (window.scrollY > 8) {
        nav.style.boxShadow = "0 10px 30px rgba(0, 0, 0, 0.35)";
      } else {
        nav.style.boxShadow = "none";
      }
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }
})();
