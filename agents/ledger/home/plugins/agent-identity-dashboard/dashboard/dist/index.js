(function () {
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const { React } = SDK;
  const { useEffect, useState } = SDK.hooks;

  function pickIdentity(config) {
    const dashboard = (config && config.dashboard) || {};
    const startup = (config && config.startup_agent) || {};
    const name = dashboard.agent_name || startup.name || "Hermes Agent";
    const role = dashboard.agent_role || startup.role || "";
    const title = dashboard.title || `${name} Dashboard`;
    return { name, role, title };
  }

  function useIdentity() {
    const [identity, setIdentity] = useState({
      name: "Hermes Agent",
      role: "",
      title: "Hermes Dashboard",
    });

    useEffect(() => {
      let cancelled = false;
      SDK.fetchJSON("/api/config")
        .then((config) => {
          if (cancelled) return;
          const next = pickIdentity(config);
          setIdentity(next);
          if (next.title) document.title = next.title;
        })
        .catch(() => {});
      return () => { cancelled = true; };
    }, []);

    return identity;
  }

  function HeaderBanner() {
    const identity = useIdentity();
    return React.createElement(
      "div",
      { className: "agent-identity-banner" },
      React.createElement("span", { className: "agent-identity-banner-label" }, identity.name),
      identity.role
        ? React.createElement("span", { className: "agent-identity-banner-role" }, identity.role)
        : null,
    );
  }

  window.__HERMES_PLUGINS__.register("agent-identity-dashboard", function AgentIdentityPage() {
    return null;
  });
  window.__HERMES_PLUGINS__.registerSlot("agent-identity-dashboard", "header-banner", HeaderBanner);
})();
