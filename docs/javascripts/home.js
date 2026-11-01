/* Landing page download links.
 *
 * Reads the latest desktop release from the GitHub API and points every
 * download link straight at its installer, so the browser starts the download
 * without opening the release page. The primary button gets the installer for
 * the visitor's system. Without JavaScript, or if the API is unavailable, the
 * links keep their fallback: the latest release page.
 */
(function () {
  "use strict";

  var REPO = "aryanjsx/Locus";
  var CACHE_KEY = "locus-latest-desktop-release";
  var CACHE_MS = 10 * 60 * 1000;

  // Installer file names follow Tauri's conventions, e.g.
  // Locus_1.0.5_x64-setup.exe or Locus-1.0.5-1.x86_64.rpm.
  var ASSETS = {
    "win-x64": { pattern: /_x64-setup\.exe$/i, label: "Download for Windows", system: "Windows 10 and 11, 64-bit" },
    "win-msi": { pattern: /_x64_[a-z-]+\.msi$/i },
    "win-arm64": { pattern: /_arm64-setup\.exe$/i, label: "Download for Windows on ARM", system: "Windows 11 on ARM" },
    "mac": { pattern: /_universal\.dmg$/i, label: "Download for macOS", system: "macOS 10.15 or later" },
    "linux-appimage": { pattern: /_amd64\.AppImage$/i, label: "Download for Linux", system: "Linux, x86-64 AppImage" },
    "linux-deb": { pattern: /_amd64\.deb$/i },
    "linux-rpm": { pattern: /\.x86_64\.rpm$/i },
  };

  function formatSize(bytes) {
    return bytes >= 1024 * 1024 * 1024
      ? (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB"
      : Math.round(bytes / (1024 * 1024)) + " MB";
  }

  function versionOf(release) {
    return release.tag_name.replace(/^desktop-v/, "");
  }

  // Published desktop releases, newest first. CLI-only tags and the rolling
  // pre-release channels (desktop-edge, desktop-latest) are skipped.
  function fetchReleases() {
    try {
      var cached = JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null");
      if (cached && Date.now() - cached.at < CACHE_MS) return Promise.resolve(cached.releases);
    } catch (e) {
      /* storage unavailable: fetch instead */
    }
    return fetch("https://api.github.com/repos/" + REPO + "/releases?per_page=20", {
      headers: { Accept: "application/vnd.github+json" },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("GitHub API returned " + resp.status);
        return resp.json();
      })
      .then(function (releases) {
        var slim = releases
          .filter(function (r) {
            return !r.draft && !r.prerelease && /^desktop-v\d/.test(r.tag_name);
          })
          .map(function (r) {
            return {
              tag_name: r.tag_name,
              html_url: r.html_url,
              published_at: r.published_at,
              assets: r.assets.map(function (a) {
                return { name: a.name, size: a.size, url: a.browser_download_url };
              }),
            };
          });
        if (!slim.length) throw new Error("No desktop release published yet");
        try {
          sessionStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), releases: slim }));
        } catch (e) {
          /* not cached; fine */
        }
        return slim;
      });
  }

  // Best guess at the visitor's installer. Windows on ARM can only be told
  // apart through User-Agent Client Hints (Chromium browsers).
  function detectSystem() {
    var uaData = navigator.userAgentData;
    var platform = ((uaData && uaData.platform) || navigator.platform || "").toLowerCase();
    var ua = navigator.userAgent.toLowerCase();

    if (/android|iphone|ipad|ipod/.test(ua) || (uaData && uaData.mobile)) {
      return Promise.resolve("mobile");
    }
    if (platform.indexOf("win") === 0 || ua.indexOf("windows") !== -1) {
      if (uaData && uaData.getHighEntropyValues) {
        return uaData
          .getHighEntropyValues(["architecture"])
          .then(function (v) {
            return v.architecture === "arm" ? "win-arm64" : "win-x64";
          })
          .catch(function () {
            return "win-x64";
          });
      }
      return Promise.resolve(/arm64|aarch64/.test(ua) ? "win-arm64" : "win-x64");
    }
    if (platform.indexOf("mac") === 0 || ua.indexOf("mac os") !== -1) return Promise.resolve("mac");
    if (platform.indexOf("linux") !== -1 || ua.indexOf("linux") !== -1) return Promise.resolve("linux-appimage");
    return Promise.resolve(null);
  }

  // The newest installer for `key`. If the latest release is missing one
  // platform (its build failed, say), fall back to the newest release that
  // has it, so the link is still a direct download.
  function findAsset(releases, key) {
    var pattern = ASSETS[key] && ASSETS[key].pattern;
    if (!pattern) return null;
    for (var i = 0; i < releases.length; i++) {
      var asset = releases[i].assets.find(function (a) {
        return pattern.test(a.name);
      });
      if (asset) return { asset: asset, release: releases[i] };
    }
    return null;
  }

  function fillTable(releases, yours) {
    var latest = releases[0];
    document.querySelectorAll("[data-asset]").forEach(function (row) {
      var key = row.getAttribute("data-asset");
      var found = findAsset(releases, key);
      var link = row.querySelector("[data-link]");
      var size = row.querySelector("[data-size]");
      row.classList.toggle("is-yours", key === yours);
      if (found) {
        link.href = found.asset.url;
        link.textContent = "Download";
        link.setAttribute("aria-label", "Download " + found.asset.name);
        size.textContent = formatSize(found.asset.size);
        if (found.release !== latest) size.textContent += " · version " + versionOf(found.release);
        row.querySelector("[data-name]").title = found.asset.name;
      } else {
        size.textContent = "Not available yet";
        link.href = latest.html_url;
        link.textContent = "See release";
      }
    });

    var line = document.querySelector("[data-release-line]");
    if (line) {
      var date = new Date(latest.published_at).toLocaleDateString(undefined, {
        year: "numeric", month: "long", day: "numeric",
      });
      line.textContent = "Version " + versionOf(latest) + ", released " + date + ".";
    }
  }

  function fillPrimary(releases, yours) {
    var button = document.querySelector("[data-download-primary]");
    var label = document.querySelector("[data-download-label]");
    var meta = document.querySelector("[data-download-meta]");
    if (!button) return;

    var found = yours && findAsset(releases, yours);
    if (yours === "mobile") {
      label.textContent = "See desktop downloads";
      button.href = "#download";
      var other = document.querySelector(".lx-get .lx-button--quiet");
      if (other) other.hidden = true;
      meta.textContent = "Locus is a desktop app for Windows, macOS and Linux.";
      return;
    }
    if (!found) {
      label.textContent = "Choose your download";
      button.href = "#download";
      meta.textContent = "Version " + versionOf(releases[0]) + " · free · no account needed";
      return;
    }
    button.href = found.asset.url;
    label.textContent = ASSETS[yours].label;
    meta.textContent =
      "Version " + versionOf(found.release) + " · " + formatSize(found.asset.size) + " · " +
      ASSETS[yours].system;
  }

  function init() {
    if (!document.querySelector("[data-download]")) return;
    Promise.all([fetchReleases(), detectSystem()])
      .then(function (results) {
        fillPrimary(results[0], results[1]);
        fillTable(results[0], results[1]);
      })
      .catch(function () {
        // Keep the fallback links to the latest release page.
        var meta = document.querySelector("[data-download-meta]");
        if (meta) meta.textContent = "Free · opens the latest release on GitHub";
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
