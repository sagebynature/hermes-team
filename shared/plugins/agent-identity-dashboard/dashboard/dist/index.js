(function () {
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const { React } = SDK;
  const { useEffect, useState } = SDK.hooks;
  const PLUGIN_NAME = "agent-identity-dashboard";
  const PROFILE_URL = "/api/plugins/agent-identity-dashboard/profile.jpg";
  const DEFAULT_BRAND_TEXT = "TEAM NEXUS";
  const DEFAULT_BRAND_HTML = "TEAM NEXUS";
  const DEFAULT_THEME_COLORS = { primary: "#50ff50", secondary: "#ff9830" };

  function pickIdentity(config) {
    const dashboard = (config && config.dashboard) || {};
    const startup = (config && config.startup_agent) || {};
    const name = dashboard.agent_name || startup.name || "Hermes Agent";
    const role = dashboard.agent_role || startup.role || "";
    const title = dashboard.title || `Team Nexus: ${name}`;
    return { name, role, title };
  }

  function normalizeHex(value) {
    if (typeof value !== "string") return null;
    const text = value.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(text)) return text.toLowerCase();
    if (/^[0-9a-fA-F]{6}$/.test(text)) return `#${text.toLowerCase()}`;
    return null;
  }

  function hexToRgb(value) {
    const hex = normalizeHex(value);
    if (!hex) return null;
    return [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
  }

  function normalizeThemeColors(colors) {
    const primary = normalizeHex(colors && colors.primary) || DEFAULT_THEME_COLORS.primary;
    const secondary = normalizeHex(colors && colors.secondary) || DEFAULT_THEME_COLORS.secondary;
    return { primary, secondary };
  }

  function applyAgentThemeColors(colors) {
    const theme = normalizeThemeColors(colors);
    const root = document.documentElement;
    const primaryRgb = hexToRgb(theme.primary) || [80, 255, 80];
    const secondaryRgb = hexToRgb(theme.secondary) || [255, 152, 48];
    root.style.setProperty("--agent-primary-color", theme.primary);
    root.style.setProperty("--agent-secondary-color", theme.secondary);
    root.style.setProperty("--agent-primary-rgb", primaryRgb.join(", "));
    root.style.setProperty("--agent-secondary-rgb", secondaryRgb.join(", "));
    root.style.setProperty("--foreground", theme.primary);
    root.style.setProperty("--primary", theme.primary);
    root.style.setProperty("--ring", theme.primary);
    root.style.setProperty("--secondary", `rgba(${secondaryRgb.join(", ")}, 0.12)`);
    root.dataset.agentPrimaryColor = theme.primary;
    root.dataset.agentSecondaryColor = theme.secondary;
    return theme;
  }

  function normalizeIdentity(payload) {
    const profile = payload && payload.profile_image;
    return {
      name: (payload && payload.name) || "Hermes Agent",
      role: (payload && payload.role) || "",
      title: (payload && payload.title) || "Hermes Dashboard",
      hasProfileImage: Boolean(profile && profile.available),
      profileUrl: (profile && profile.url) || PROFILE_URL,
      themeColors: normalizeThemeColors(payload && payload.dashboard_colors),
    };
  }

  function useIdentity() {
    const [identity, setIdentity] = useState({
      name: "Hermes Agent",
      role: "",
      title: "Hermes Dashboard",
      hasProfileImage: false,
      profileUrl: PROFILE_URL,
      themeColors: DEFAULT_THEME_COLORS,
    });

    useEffect(() => {
      let cancelled = false;

      SDK.fetchJSON(`/api/plugins/${PLUGIN_NAME}/identity`)
        .then((payload) => {
          if (cancelled) return;
          const next = normalizeIdentity(payload);
          applyAgentThemeColors(next.themeColors);
          setIdentity(next);
          if (next.title) document.title = next.title;
        })
        .catch(() => {
          SDK.fetchJSON("/api/config")
            .then((config) => {
              if (cancelled) return;
              const dashboard = (config && config.dashboard) || {};
              const next = {
                ...pickIdentity(config),
                hasProfileImage: false,
                profileUrl: PROFILE_URL,
                themeColors: normalizeThemeColors(dashboard.accent_colors || {
                  primary: dashboard.primary_color,
                  secondary: dashboard.secondary_color,
                }),
              };
              applyAgentThemeColors(next.themeColors);
              setIdentity(next);
              if (next.title) document.title = next.title;
            })
            .catch(() => {});
        });

      return () => { cancelled = true; };
    }, []);

    return identity;
  }

  function profileImageUrl(identity) {
    return `${identity.profileUrl}${identity.profileUrl.includes("?") ? "&" : "?"}v=${Date.now()}`;
  }

  function findSidebarRoot() {
    return (
      document.querySelector("#app-sidebar") ||
      document.querySelector('[data-sidebar="sidebar"]') ||
      document.querySelector('[data-sidebar]') ||
      document.querySelector("aside")
    );
  }

  function findSystemAnchor(sidebar) {
    const candidates = sidebar.querySelectorAll(
      '[data-sidebar="group-label"], [role="heading"], h2, h3, p, span, div'
    );
    for (const candidate of candidates) {
      if ((candidate.textContent || "").trim().toLowerCase() !== "system") continue;
      return candidate.closest('[data-sidebar="group"], li, section, nav > div, div') || candidate;
    }
    return null;
  }

  function upsertDefaultBrand() {
    const sidebar = findSidebarRoot();
    if (!sidebar) return false;

    const header = sidebar.querySelector(":scope > div:first-child");
    if (!header) return false;

    const candidates = [
      ...header.querySelectorAll("span"),
      ...header.querySelectorAll("a"),
      ...header.querySelectorAll(":scope > div"),
    ];
    for (const candidate of candidates) {
      const normalized = (candidate.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      const compact = normalized.replace(/\s+/g, "");
      const currentBrand = compact === "hermesagent" || compact === "teamnexus";
      if (!currentBrand) continue;
      if (compact === "teamnexus" && candidate.dataset.agentBrand === "team-nexus") return true;
      candidate.innerHTML = DEFAULT_BRAND_HTML;
      candidate.dataset.agentBrand = "team-nexus";
      candidate.setAttribute("aria-label", DEFAULT_BRAND_TEXT);
      candidate.title = DEFAULT_BRAND_TEXT;
      return true;
    }

    return false;
  }

  function removeLegacyBanner() {
    document.querySelectorAll(".agent-identity-banner, .agent-dashboard-nav").forEach((element) => element.remove());
  }

  function upsertSidebarIdentity(identity) {
    const existing = document.querySelector(".agent-sidebar-identity");
    if (!identity.hasProfileImage) {
      if (existing) existing.remove();
      return false;
    }

    const sidebar = findSidebarRoot();
    if (!sidebar) return false;
    const anchor = findSystemAnchor(sidebar);
    if (!anchor || !anchor.parentElement) return false;

    const key = JSON.stringify({
      name: identity.name || "",
      role: identity.role || "",
      title: identity.title || "",
      profileUrl: identity.profileUrl || "",
    });
    const alreadyPlaced = existing && existing.parentElement === anchor.parentElement && existing.nextElementSibling === anchor;
    if (existing && existing.dataset.identityKey === key && alreadyPlaced) return true;

    const card = existing || document.createElement("a");
    card.className = "agent-sidebar-identity";
    card.dataset.identityKey = key;
    card.href = "/sessions";
    card.title = identity.title || identity.name || "Agent dashboard";
    card.setAttribute("aria-label", card.title);
    card.innerHTML = "";

    const image = document.createElement("img");
    image.className = "agent-sidebar-identity-image";
    image.src = profileImageUrl(identity);
    image.alt = identity.name || "Agent profile";
    card.appendChild(image);

    const copy = document.createElement("span");
    copy.className = "agent-sidebar-identity-copy";

    const name = document.createElement("span");
    name.className = "agent-sidebar-identity-name";
    name.textContent = identity.name || "Hermes Agent";
    copy.appendChild(name);

    if (identity.role) {
      const role = document.createElement("span");
      role.className = "agent-sidebar-identity-role";
      role.textContent = identity.role;
      copy.appendChild(role);
    }

    card.appendChild(copy);

    if (!existing || existing.parentElement !== anchor.parentElement) {
      anchor.parentElement.insertBefore(card, anchor);
    }
    return true;
  }

  function useSidebarIdentity(identity) {
    useEffect(() => {
      let disposed = false;
      let frame = 0;

      const sync = () => {
        if (disposed) return;
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          removeLegacyBanner();
          upsertDefaultBrand();
          upsertSidebarIdentity(identity);
        });
      };

      sync();
      const observer = new MutationObserver(sync);
      observer.observe(document.body, { childList: true, subtree: true });

      return () => {
        disposed = true;
        cancelAnimationFrame(frame);
        observer.disconnect();
        const existing = document.querySelector(".agent-sidebar-identity");
        if (existing) existing.remove();
        removeLegacyBanner();
      };
    }, [identity.hasProfileImage, identity.name, identity.role, identity.title, identity.profileUrl]);
  }

  function IdentityEffects() {
    const identity = useIdentity();
    useSidebarIdentity(identity);
    return null;
  }

  window.__HERMES_PLUGINS__.register(PLUGIN_NAME, function AgentIdentityPage() {
    return null;
  });
  window.__HERMES_PLUGINS__.registerSlot(PLUGIN_NAME, "header-banner", IdentityEffects);
})();
