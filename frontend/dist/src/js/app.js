/* NEXUS core app: boot, auth, routing, global chrome */
(function () {
  const APP = (window.NEXUS_APP = { pages: {} });
  const pageCache = {};
  let currentPage = null;
  let refreshTimer = null;

  document.addEventListener("DOMContentLoaded", init);

  /* ---------------------------------------------------------------
   * Global error boundary: never let an unexpected frontend error
   * blank the screen. Show a toast and keep the SPA usable.
   * --------------------------------------------------------------- */
  function installErrorBoundary() {
    window.addEventListener("error", (e) => {
      try {
        UI.toast("An unexpected error occurred. The app will continue.", "error", 6000);
      } catch (_) {}
      console.error("[NEXUS] uncaught error:", e.message || e);
    });
    window.addEventListener("unhandledrejection", (e) => {
      try {
        UI.toast("Something failed silently. Please try again.", "error", 5000);
      } catch (_) {}
      console.error("[NEXUS] unhandled rejection:", (e && e.reason) || e);
    });
  }

  function bind(x, name) {
    const el = document.getElementById(name);
    if (el) x.apply(el);
    return el;
  }

  async function init() {
    installErrorBoundary();
    bindGlobalChrome();
    wireLogin();
    wireRouter();

    if (NEXUS.token) {
      try {
        const me = await NEXUS.me();
        syncUser(me);
        enterApp(routerPageFromHash());
      } catch (e) {
        NEXUS.clearAuth();
        handleRoute();
      }
    } else {
      handleRoute();
    }
  }

  /* ---------- helpers ---------- */
  function stripHash() {
    try {
      history.replaceState(null, "", window.location.pathname + window.location.search);
    } catch (_) {}
  }

  function routerPageFromHash() {
    const raw = (window.location.hash.replace(/^#\/?/, "") || window.location.pathname.replace(/^\//, "")).toLowerCase();
    const authPages = ["login", "signin", "signup", "register"];
    if (authPages.includes(raw) || !raw) return "overview";
    return raw;
  }

  function requireListener(id, fn) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", fn);
    return el;
  }

  function setVisible(sel, visible) {
    document.querySelectorAll(sel).forEach((el) => {
      el.classList.toggle("hidden", !visible);
    });
  }

  function enterApp(page) {
    // Hide the auth screens. Root-cause fix: never assume an element with a
    // hard-coded id exists — operate on the class that actually gates visibility.
    document.querySelectorAll(".auth-screen").forEach((s) => s.classList.remove("active-screen"));

    const shell = document.getElementById("app-shell");
    if (shell) shell.classList.add("visible");
    if (!NEXUS.user) {
      doLogout();
      return;
    }
    syncUser(NEXUS.user);

    // Show/hide admin nav
    const isAdmin = NEXUS.user.role === "ADMIN";
    document.querySelectorAll("[data-admin-only]").forEach((el) => {
      el.style.display = isAdmin ? "" : "none";
    });

    navigate(page || "overview");
    loadNotifications();
    startAutorefresh();
  }

  function syncUser(u) {
    if (!u) return;
    NEXUS.user = u;
    const initials = (u.full_name || u.username || "U")
      .split(/\s+/)
      .map((s) => s[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
    const avatar = document.getElementById("profile-avatar");
    const name = document.getElementById("profile-name");
    const role = document.getElementById("profile-role");
    if (avatar) avatar.textContent = initials;
    if (name) name.textContent = u.full_name || u.username || "User";
    if (role) role.textContent = u.role || "VIEWER";
  }

  /* ---------- Auth screens ---------- */
  function showLogin() {
    showAuthScreen("login");
  }

  function showLoginError(msg) {
    const activeScreen = document.querySelector(".auth-screen.active-screen");
    if (activeScreen) {
      const el = activeScreen.querySelector(".auth-error");
      if (el) {
        el.textContent = msg || "";
        el.classList.toggle("hidden", !msg);
      }
    }
    if (!msg) {
      document.querySelectorAll(".auth-error").forEach((el) => {
        el.textContent = "";
        el.classList.add("hidden");
      });
    }
  }

  function showAuthScreen(screen, email, purpose, note) {
    document.querySelectorAll(".auth-screen").forEach((s) => s.classList.remove("active-screen"));
    const target = document.getElementById("auth-" + screen);
    if (target) {
      target.classList.add("active-screen");
      if (email) {
        const display = target.querySelector("[data-email-display]");
        if (display) {
          display.textContent = email;
          display.dataset.email = email;
        }
      }
      if (purpose) {
        const pField = target.querySelector("[data-purpose]");
        if (pField) pField.value = purpose;
      }
      const noteEl = target.querySelector("[data-auth-note]");
      if (noteEl) {
        noteEl.textContent = note || "";
        noteEl.classList.toggle("hidden", !note);
      }
    }
    showLoginError("");
  }

  function spinnerFor(id, on) {
    UI.spinnerButton(document.getElementById(id), on);
  }

  function wireLogin() {
    // ---- Login ----
    bind(() => {
      this.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("login-email").value.trim();
        const password = document.getElementById("login-password").value;
        const remember = document.getElementById("remember-me").checked;
        showLoginError("");
        if (!email || !password) {
          showLoginError("Please enter your email and password.");
          return;
        }
        spinnerFor("login-btn", true);
        try {
          const res = await NEXUS.login(email, password, remember);
          NEXUS.setAuth(res.access_token, res.user);
          syncUser(res.user);
          UI.toast("Welcome back, " + (res.user.full_name || res.user.username) + "!", "success");
          enterApp("overview");
        } catch (err) {
          showLoginError(err.message || "Login failed. Check your credentials.");
        } finally {
          spinnerFor("login-btn", false);
        }
      });
    }, "login-form");

    requireListener("demo-login-btn", async (e) => {
      const btn = e.currentTarget;
      UI.spinnerButton(btn, true);
      try {
        const res = await NEXUS.demoLogin();
        NEXUS.setAuth(res.access_token, res.user);
        syncUser(res.user);
        UI.toast("Logged in with demo account (synthetic data)", "success");
        enterApp("overview");
      } catch (err) {
        UI.toast(err.message || "Demo login failed", "error");
      } finally {
        UI.spinnerButton(btn, false);
      }
    });

    requireListener("signup-link", (e) => {
      e.preventDefault();
      showAuthScreen("signup");
    });

    // "Already have an account? Sign in" / "Back to sign in" (login and
    // signup screens). Bound via document delegation so the navigation always
    // works regardless of when an element mounts.
    document.addEventListener("click", (e) => {
      const backBtn = e.target && e.target.closest ? e.target.closest("[data-back-login]") : null;
      if (!backBtn) return;
      e.preventDefault();
      showAuthScreen("login");
    });

    // ---- Signup form ----
    const signupForm = document.getElementById("signup-form");
    if (signupForm) {
      signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("signup-email").value.trim();
        const username = document.getElementById("signup-username").value.trim();
        const fullName = document.getElementById("signup-fullname").value.trim();
        const password = document.getElementById("signup-password").value;
        const confirmPw = document.getElementById("signup-confirm-password").value;
        showLoginError("");
        if (!fullName) {
          showLoginError("Full name is required.");
          return;
        }
        if (!email || !username || !password) {
          showLoginError("All fields are required.");
          return;
        }
        if (password !== confirmPw) {
          showLoginError("Passwords do not match.");
          return;
        }
        spinnerFor("signup-btn", true);
        try {
          const res = await NEXUS.register(email, username, fullName, password, confirmPw);
          // Registration auto-authenticates the new account — straight into the app.
          NEXUS.setAuth(res.access_token, res.user);
          syncUser(res.user);
          UI.toast("Account created. Welcome, " + (res.user.full_name || res.user.username) + "!", "success");
          enterApp("overview");
        } catch (err) {
          // An account already owns this email. Never create a duplicate.
          if (err.status === 409) {
            showLoginError("An account with this email already exists. Please sign in.");
            return;
          }
          showLoginError(err.message || "Registration failed.");
        } finally {
          spinnerFor("signup-btn", false);
        }
      });
    }
  }

  /* ---------- Routing ---------- */
  function wireRouter() {
    window.addEventListener("hashchange", () => {
      const hash = window.location.hash.replace("#", "") || "overview";
      if (!NEXUS.token) {
        // An unauthenticated user must not reach protected pages.
        stripHash();
        showAuthScreen("login");
        return;
      }
      navigate(hash);
    });

    document.querySelectorAll("[data-nav]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const target = a.dataset.page || (a.getAttribute("href") || "#overview").replace("#", "");
        navigate(target);
        if (window.innerWidth <= 900) {
          const shell = document.getElementById("app-shell");
          if (shell) shell.classList.remove("sidebar-open");
        }
      });
    });

    const sbToggle = document.getElementById("sidebar-toggle");
    if (sbToggle) {
      sbToggle.addEventListener("click", () => {
        const shell = document.getElementById("app-shell");
        if (!shell) return;
        if (window.innerWidth <= 900) {
          shell.classList.toggle("sidebar-open");
        } else {
          shell.classList.toggle("sidebar-collapsed");
        }
      });
    }
  }

  function canAccessPage(page) {
    if (page === "admin") {
      return !!(NEXUS.user && NEXUS.user.role === "ADMIN");
    }
    return true;
  }

  async function navigate(page) {
    if (page === "logout") {
      doLogout();
      return;
    }
    if (!NEXUS.token) {
      stripHash();
      showAuthScreen("login");
      return;
    }
    // Backend authorization is authoritative; the client guard just avoids
    // rendering a panel the user has no permission to view.
    if (!canAccessPage(page)) {
      UI.toast("Admin access required.", "error");
      page = "overview";
    }

    currentPage = page;
    try {
      history.replaceState(null, "", "#" + page);
    } catch (_) {}

    if (!APP.pages[page]) APP.pages[page] = {};

    document.querySelectorAll("[data-nav], .sidebar-nav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.page === page);
    });

    const section = document.querySelector(`.page[data-page-id="${page}"]`);
    if (!section) return;

    try {
      if (!(page in pageCache)) {
        const res = await fetch(`./src/pages/${page}.html`);
        pageCache[page] = res.ok
          ? await res.text()
          : `<div class="empty-state">Page template missing: ${page}.</div>`;
      }
      section.innerHTML = pageCache[page];

      document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
      section.classList.add("active");

      bindGenericActions(section);

      const renderer = APP.pages[page].render || window["NexusPage_" + page];
      if (renderer) {
        await renderer(section);
      }

      section.querySelectorAll("[data-close-modal]").forEach((el) => {
        el.addEventListener("click", closeAllModals);
      });
    } catch (e) {
      console.warn("Failed to render page", page, e);
      section.innerHTML = `<div class="empty-state">Something went wrong rendering this page.</div>`;
    }
  }

  function bindGenericActions(scope) {
    scope.querySelectorAll("[data-action]").forEach((el) => {
      const action = el.dataset.action;
      el.addEventListener("click", () => {
        const fn = window["NexusAction_" + action];
        if (fn) fn(el);
        else UI.toast("Action not wired yet: " + action, "error");
      });
    });
    scope.querySelectorAll("[data-toast]").forEach((el) => {
      el.addEventListener("click", () => UI.toast(el.dataset.toast));
    });
    scope.querySelectorAll("[data-close-modal]").forEach((el) => {
      el.addEventListener("click", closeAllModals);
    });
  }

  function closeAllModals() {
    document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
  }

  /* ---------- Global chrome ---------- */
  function bindGlobalChrome() {
    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) logoutBtn.addEventListener("click", doLogout);

    const notifBtn = document.getElementById("notif-btn");
    if (notifBtn) notifBtn.addEventListener("click", toggleNotifPanel);

    const settingsBtn = document.getElementById("settings-btn");
    if (settingsBtn) {
      settingsBtn.addEventListener("click", () => {
        const modal = document.getElementById("settings-modal");
        if (!modal) return;
        modal.classList.remove("hidden");
        const email = document.getElementById("settings-email");
        const role = document.getElementById("settings-role");
        if (email) email.value = (NEXUS.user && NEXUS.user.email) || "";
        if (role) role.textContent = (NEXUS.user && NEXUS.user.role) || "VIEWER";
        const density = document.getElementById("settings-density");
        if (density) {
          density.onchange = (e) => {
            document.body.style.fontSize = e.target.value === "compact" ? "13px" : "14px";
          };
        }
      });
    }

    const profileBtn = document.getElementById("profile-btn");
    if (profileBtn) {
      profileBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleProfileMenu();
      });
    }

    document.querySelectorAll("[data-close-modal]").forEach((el) => el.addEventListener("click", closeAllModals));

    document.addEventListener("click", (e) => {
      const panel = document.getElementById("notif-panel");
      if (panel && !panel.classList.contains("hidden") && !e.target.closest("#notif-btn")) {
        panel.classList.add("hidden");
      }
      const menu = document.getElementById("profile-menu");
      if (menu && !menu.classList.contains("hidden") && !e.target.closest("#profile-btn")) {
        menu.classList.add("hidden");
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.metaKey && currentPage === "command") {
        const submit = document.getElementById("command-submit");
        if (submit) submit.click();
      }
    });
  }

  function doLogout() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    if (NEXUS.token) {
      try {
        NEXUS.logout().catch(() => {});
      } catch (e) {}
    }
    NEXUS.clearAuth();
    const shell = document.getElementById("app-shell");
    if (shell) shell.classList.remove("visible");
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    stripHash();
    showAuthScreen("login");
    UI.toast("Signed out");
  }

  function toggleNotifPanel() {
    const panel = document.getElementById("notif-panel");
    if (!panel) return;
    if (panel.classList.contains("hidden")) {
      loadNotifications();
      panel.classList.remove("hidden");
    } else {
      panel.classList.add("hidden");
    }
  }

  function toggleProfileMenu() {
    const menu = document.getElementById("profile-menu");
    if (!menu) return;
    if (menu.classList.contains("hidden")) {
      const u = NEXUS.user || {};
      menu.innerHTML = `
        <button data-profile-info><strong>${(u.full_name || u.username || "User").replace(/</g, "&lt;")}</strong><br><span style="font-size:11px;color:var(--text-3)">${(u.email || "").replace(/</g, "&lt;")}</span></button>
        <hr>
        <button data-action-settings>⚙ Settings</button>
        <button data-action-logout>⇥ Logout</button>`;
      menu.querySelector("[data-action-settings]").addEventListener("click", () => {
        menu.classList.add("hidden");
        if (document.getElementById("settings-btn")) document.getElementById("settings-btn").click();
      });
      menu.querySelector("[data-action-logout]").addEventListener("click", () => {
        menu.classList.add("hidden");
        doLogout();
      });
      menu.classList.remove("hidden");
    } else {
      menu.classList.add("hidden");
    }
  }

  async function loadNotifications() {
    try {
      const res = await NEXUS.notifications();
      renderNotificationBadge(res.notifications || []);
      renderNotifPanel(res.notifications || []);
    } catch (e) {
      renderNotificationBadge([]);
    }
  }

  function renderNotificationBadge(notifs) {
    const badge = document.getElementById("notif-badge");
    if (!badge) return;
    const unread = (notifs || []).filter((n) => !n.read).length;
    if (unread > 0) {
      badge.textContent = unread > 99 ? "99+" : unread;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }

  function renderNotifPanel(notifs) {
    const panel = document.getElementById("notif-panel");
    if (!panel) return;
    if (!notifs.length) {
      panel.innerHTML = `<div class="empty-state">No notifications yet.</div>`;
      return;
    }
    const items = notifs
      .slice(0, 30)
      .map((n) => {
        const sev = n.severity || "INFO";
        return `
        <div class="notif-item ${n.read ? "" : "unread"}" data-notif="${n.id}">
          <span class="notif-dot ${sev}"></span>
          <div>
            <div class="notif-title">${fmt.text(n.title)}</div>
            <div class="notif-msg">${fmt.text(n.message)}</div>
            <div class="notif-time">${fmt.time(n.created_at)} · ${n.category || "general"}</div>
          </div>
        </div>`;
      })
      .join("");

    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <h3 style="font-size:14px;">Notifications</h3>
        <button class="btn btn-ghost" style="padding:5px 10px;font-size:11px;" id="notif-mark-all">Mark all read</button>
      </div>
      ${items}
      <div style="display:flex;justify-content:center;margin-top:8px;">
        <button class="btn btn-ghost" style="padding:5px 10px;font-size:11px;" data-close-panel>Close</button>
      </div>`;

    panel.querySelectorAll(".notif-item").forEach((item) => {
      item.addEventListener("click", async () => {
        const id = item.dataset.notif;
        try {
          await NEXUS.markNotification(id);
          loadNotifications();
        } catch (_) {}
      });
    });

    const markAll = panel.querySelector("#notif-mark-all");
    if (markAll) {
      markAll.addEventListener("click", async () => {
        try {
          await NEXUS.markAllRead();
          loadNotifications();
        } catch (_) {}
      });
    }
    const closeBtn = panel.querySelector("[data-close-panel]");
    if (closeBtn) closeBtn.addEventListener("click", () => panel.classList.add("hidden"));
  }

  /* ---------- Autorefresh ---------- */
  function startAutorefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      if (document.hidden) return;
      if (!NEXUS.token) return;
      const autorefresh = document.getElementById("settings-autorefresh");
      if (autorefresh && !autorefresh.checked) return;
      if (currentPage && APP.pages[currentPage] && APP.pages[currentPage].autorefresh) {
        APP.pages[currentPage].autorefresh();
      }
    }, 60000);
  }

  /* Page renderer registration helper */
  APP.register = function (page, renderer, autorefresh) {
    APP.pages[page] = { render: renderer, autorefresh };
  };
  APP.rebind = function (scope) {
    bindGenericActions(scope);
  };
})();