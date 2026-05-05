(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !SDK.React) {
    console.error("Team Router: missing plugin SDK");
    return;
  }
  const React = SDK.React;
  const h = React.createElement;
  const { useCallback, useEffect, useState } = React;
  const UI = SDK.components || SDK.ui || {};
  const API = "/api/plugins/team-router";

  function join() { return Array.prototype.slice.call(arguments).filter(Boolean).join(" "); }
  function fallback(tag, base) {
    return function Fallback(props) {
      const next = Object.assign({}, props || {});
      const children = next.children;
      delete next.children;
      const cls = join(base, next.className);
      next.className = cls;
      return h(tag, next, children);
    };
  }
  const Card = UI.Card || fallback("section", "tr-card");
  const CardHeader = UI.CardHeader || fallback("div", "tr-card-header");
  const CardTitle = UI.CardTitle || fallback("h3", "tr-card-title");
  const CardContent = UI.CardContent || fallback("div", "tr-card-content");
  const Button = UI.Button || fallback("button", "tr-button");

  function fetchJSON(path) {
    if (SDK.fetchJSON) return SDK.fetchJSON(path);
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  function compact(value) { return String(Number(value || 0)); }
  function short(value, n) {
    const s = String(value || "");
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }
  function pill(status) { return h("span", { className: "tr-pill tr-pill--" + String(status || "unknown") }, status || "unknown"); }

  function Kpi(props) {
    return h("div", { className: "tr-kpi" },
      h("div", { className: "tr-label" }, props.label),
      h("div", { className: "tr-value" }, props.value),
      props.note ? h("div", { className: "tr-note" }, props.note) : null
    );
  }

  function Checks(props) {
    const checks = props.checks || [];
    return h(Card, null,
      h(CardHeader, null, h(CardTitle, null, "Health Checks")),
      h(CardContent, null,
        checks.length ? checks.map(function (c) {
          return h("div", { key: c.name, className: "tr-check" },
            h("span", { className: c.ok ? "tr-dot tr-dot--ok" : "tr-dot tr-dot--bad" }),
            h("div", null,
              h("div", { className: "tr-check-name" }, c.name.replace(/_/g, " ")),
              h("div", { className: "tr-note" }, c.detail || "")
            )
          );
        }) : h("p", { className: "tr-note" }, "No checks returned yet.")
      )
    );
  }

  function Recent(props) {
    const rows = props.rows || [];
    return h(Card, { className: "tr-span" },
      h(CardHeader, null, h(CardTitle, null, "Recent Router Messages")),
      h(CardContent, null,
        rows.length ? h("div", { className: "tr-table-wrap" },
          h("table", { className: "tr-table" },
            h("thead", null, h("tr", null,
              h("th", null, "Message"), h("th", null, "Route"), h("th", null, "Status"), h("th", null, "Kanban"), h("th", null, "Summary")
            )),
            h("tbody", null, rows.map(function (m) {
              return h("tr", { key: m.id },
                h("td", null, h("button", { className: "tr-link", onClick: function () { props.onConversation(m.conversation_id); } }, short(m.id, 28))),
                h("td", null, (m.sender || m.from) + " → " + (m.recipient || m.to)),
                h("td", null, pill(m.status)),
                h("td", null, m.kanban_task_id || "—"),
                h("td", null, short(m.summary, 96))
              );
            }))
          )
        ) : h("p", { className: "tr-note" }, "No router messages yet.")
      )
    );
  }

  function Problems(props) {
    const problems = props.problems || [];
    return h(Card, null,
      h(CardHeader, null, h(CardTitle, null, "Operator Notices")),
      h(CardContent, null,
        problems.length ? problems.map(function (p, i) {
          return h("div", { key: p.kind + i, className: "tr-problem" },
            h("div", { className: "tr-check-name" }, p.kind.replace(/_/g, " ")),
            h("div", { className: "tr-note" }, p.message || ""),
            p.items ? h("pre", null, JSON.stringify(p.items, null, 2)) : null
          );
        }) : h("p", { className: "tr-note" }, "No router notices.")
      )
    );
  }

  function Conversation(props) {
    const data = props.data;
    if (!data) return null;
    return h(Card, { className: "tr-span" },
      h(CardHeader, null, h(CardTitle, null, "Conversation " + data.conversation_id)),
      h(CardContent, null,
        data.messages.map(function (m) {
          return h("div", { key: m.id, className: "tr-conv" },
            h("div", { className: "tr-conv-head" },
              h("strong", null, m.id), pill(m.status), h("span", null, (m.from || m.sender) + " → " + (m.to || m.recipient))
            ),
            h("div", { className: "tr-note" }, m.summary),
            h("div", { className: "tr-note" }, "Kanban: " + (m.kanban_task_id || "—")),
            h("pre", null, JSON.stringify((m.events || []).slice(-5), null, 2))
          );
        })
      )
    );
  }

  function App() {
    const [status, setStatus] = useState(null);
    const [doctor, setDoctor] = useState(null);
    const [conversation, setConversation] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(false);

    const load = useCallback(function () {
      setLoading(true);
      setError(null);
      return Promise.all([fetchJSON(API + "/status"), fetchJSON(API + "/doctor")])
        .then(function (pair) { setStatus(pair[0]); setDoctor(pair[1]); })
        .catch(function (err) { setError(err && err.message ? err.message : String(err)); })
        .finally(function () { setLoading(false); });
    }, []);

    const openConversation = useCallback(function (id) {
      if (!id) return;
      fetchJSON(API + "/conversations/" + encodeURIComponent(id))
        .then(setConversation)
        .catch(function (err) { setError(err && err.message ? err.message : String(err)); });
    }, []);

    useEffect(function () { load(); }, [load]);
    useEffect(function () {
      const timer = setInterval(load, 15000);
      return function () { clearInterval(timer); };
    }, [load]);

    const counts = status && status.counts || {};
    return h("div", { className: "team-router" },
      h("section", { className: "tr-hero" },
        h("div", null,
          h("div", { className: "tr-eyebrow" }, "TEAM NEXUS STRUCTURED BUS"),
          h("h1", null, "Team Router"),
          h("p", null, "Atlas-first router observability for bounded agent coordination, Kanban linkage, and completion sync.")
        ),
        h("div", { className: "tr-actions" },
          h(Button, { onClick: load, disabled: loading }, loading ? "Refreshing" : "Refresh"),
          h("span", { className: status && status.ok ? "tr-state tr-state--ok" : "tr-state tr-state--warn" }, status && status.ok ? "healthy" : "needs attention")
        )
      ),
      error ? h("div", { className: "tr-error" }, error) : null,
      h("div", { className: "tr-grid tr-kpis" },
        h(Kpi, { label: "pending", value: compact(counts.pending) }),
        h(Kpi, { label: "dispatched", value: compact(counts.dispatched) }),
        h(Kpi, { label: "completed", value: compact(counts.completed) }),
        h(Kpi, { label: "blocked/failed", value: compact((counts.blocked || 0) + (counts.failed || 0)) }),
        h(Kpi, { label: "events", value: compact(status && status.event_count), note: status && status.generated_at })
      ),
      h("div", { className: "tr-grid" },
        h(Checks, { checks: doctor && doctor.checks }),
        h(Problems, { problems: status && status.problems })
      ),
      h(Recent, { rows: status && status.recent, onConversation: openConversation }),
      h(Conversation, { data: conversation })
    );
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("team-router", App);
  } else {
    console.error("Team Router: missing plugin registry");
  }
})();
