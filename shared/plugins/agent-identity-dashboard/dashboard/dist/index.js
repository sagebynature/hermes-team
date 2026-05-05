(function () {
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const { React } = SDK;
  const { useEffect, useState } = SDK.hooks;
  const PLUGIN_NAME = "agent-identity-dashboard";
  const PROFILE_URL = "/api/plugins/agent-identity-dashboard/profile.jpg";

  function pickIdentity(config) {
    const dashboard = (config && config.dashboard) || {};
    const startup = (config && config.startup_agent) || {};
    const name = dashboard.agent_name || startup.name || "Hermes Agent";
    const role = dashboard.agent_role || startup.role || "";
    const title = dashboard.title || `${name} Dashboard`;
    return { name, role, title };
  }

  function normalizeIdentity(payload) {
    const profile = payload && payload.profile_image;
    return {
      name: (payload && payload.name) || "Hermes Agent",
      role: (payload && payload.role) || "",
      title: (payload && payload.title) || "Hermes Dashboard",
      hasProfileImage: Boolean(profile && profile.available),
      profileUrl: (profile && profile.url) || PROFILE_URL,
    };
  }

  function useIdentity() {
    const [identity, setIdentity] = useState({
      name: "Hermes Agent",
      role: "",
      title: "Hermes Dashboard",
      hasProfileImage: false,
      profileUrl: PROFILE_URL,
    });

    useEffect(() => {
      let cancelled = false;

      SDK.fetchJSON(`/api/plugins/${PLUGIN_NAME}/identity`)
        .then((payload) => {
          if (cancelled) return;
          const next = normalizeIdentity(payload);
          setIdentity(next);
          if (next.title) document.title = next.title;
        })
        .catch(() => {
          SDK.fetchJSON("/api/config")
            .then((config) => {
              if (cancelled) return;
              const next = { ...pickIdentity(config), hasProfileImage: false, profileUrl: PROFILE_URL };
              setIdentity(next);
              if (next.title) document.title = next.title;
            })
            .catch(() => {});
        });

      return () => { cancelled = true; };
    }, []);

    useEffect(() => {
      const enabled = Boolean(identity.hasProfileImage);
      document.documentElement.classList.toggle("agent-profile-branding-active", enabled);
      document.body.classList.toggle("agent-profile-branding-active", enabled);
      return () => {
        document.documentElement.classList.remove("agent-profile-branding-active");
        document.body.classList.remove("agent-profile-branding-active");
      };
    }, [identity.hasProfileImage]);

    return identity;
  }

  function useAgentNav() {
    const [agents, setAgents] = useState([]);

    useEffect(() => {
      let cancelled = false;
      SDK.fetchJSON(`/api/plugins/${PLUGIN_NAME}/agents`)
        .then((payload) => {
          if (cancelled) return;
          setAgents(Array.isArray(payload && payload.agents) ? payload.agents : []);
        })
        .catch(() => {
          if (!cancelled) setAgents([]);
        });
      return () => { cancelled = true; };
    }, []);

    return agents;
  }

  function ProfileBrand() {
    const identity = useIdentity();
    if (!identity.hasProfileImage) return null;

    const src = `${identity.profileUrl}${identity.profileUrl.includes("?") ? "&" : "?"}v=${Date.now()}`;
    return React.createElement(
      "a",
      { className: "agent-profile-brand", href: "/sessions", title: identity.title || identity.name },
      React.createElement("img", {
        className: "agent-profile-brand-image",
        src,
        alt: identity.name || "Agent profile",
      }),
    );
  }

  function AgentNavbar() {
    const agents = useAgentNav();
    if (!agents.length) return null;

    return React.createElement(
      "nav",
      { className: "agent-dashboard-nav", "aria-label": "Agent dashboards" },
      agents.map((agent) =>
        React.createElement(
          "a",
          {
            key: agent.slug || agent.name,
            className: `agent-dashboard-nav-link${agent.current ? " is-current" : ""}`,
            href: agent.href || `/${agent.slug}/sessions`,
            title: agent.role ? `${agent.name} — ${agent.role}` : `${agent.name} dashboard`,
            "aria-current": agent.current ? "page" : undefined,
          },
          agent.name || agent.slug,
        ),
      ),
    );
  }

  function HeaderBanner() {
    const identity = useIdentity();
    return React.createElement(
      "div",
      { className: "agent-identity-banner" },
      identity.hasProfileImage
        ? React.createElement("img", {
            className: "agent-identity-mobile-image",
            src: identity.profileUrl,
            alt: "",
            "aria-hidden": "true",
          })
        : null,
      React.createElement(
        "div",
        { className: "agent-identity-banner-copy" },
        React.createElement("span", { className: "agent-identity-banner-label" }, identity.name),
        identity.role
          ? React.createElement("span", { className: "agent-identity-banner-role" }, identity.role)
          : null,
      ),
      React.createElement(AgentNavbar, null),
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN_NAME, function AgentIdentityPage() {
    return null;
  });
  window.__HERMES_PLUGINS__.registerSlot(PLUGIN_NAME, "header-left", ProfileBrand);
  window.__HERMES_PLUGINS__.registerSlot(PLUGIN_NAME, "header-banner", HeaderBanner);
})();
