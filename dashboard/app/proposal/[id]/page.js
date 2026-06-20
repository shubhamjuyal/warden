import { getProposal, listAudit } from "../../lib/db";

export const dynamic = "force-dynamic";

function fmt(ts) {
  if (!ts) return "";
  return new Date(ts).toISOString().replace("T", " ").slice(0, 19) + "Z";
}

export default async function ProposalDetail({ params }) {
  const p = await getProposal(params.id);
  if (!p) {
    return (
      <main className="wrap">
        <a className="back" href="/">← back</a>
        <div className="panel" style={{ padding: 18 }}>Proposal not found.</div>
      </main>
    );
  }
  const audit = await listAudit();
  const related = audit.entries.filter((e) => e.proposal_id === p.id);
  const actions = (p.payload && p.payload.actions) || [];

  return (
    <main className="wrap">
      <a className="back" href="/">← back to ledger</a>
      <div className="brand">
        <h1>Proposal {p.id.slice(0, 8)}</h1>
        <span className="badge">{p.capability || "—"}</span>
        <span className={`badge ${p.status}`}>{p.status}</span>
      </div>
      <p className="sub">
        <span className="kv">subject <b>{p.subject}</b></span> &nbsp;·&nbsp;
        <span className="kv">requested by <b>{p.requested_by}</b></span> &nbsp;·&nbsp;
        <span className="kv">payload hash <b>{p.payload_hash.slice(0, 16)}…</b></span>
      </p>

      <div className="grid">
        <section className="panel">
          <h2>Proposed actions ({actions.length})</h2>
          {actions.map((a, i) => (
            <div className="actionrow" key={i}>
              <div>
                <span className="atype">{a.type}</span>
                <b>{a.target}</b>
                {a.value ? <> → <code>{a.value}</code></> : null}
                <span className="pill"> &nbsp;via {a.provider}</span>
              </div>
              <div className="rationale">{a.rationale}</div>
              {a.evidence ? <div className="evidence">› {a.evidence}</div> : null}
            </div>
          ))}
        </section>

        <section className="panel">
          <h2>This proposal's audit history</h2>
          {related.map((e) => (
            <div className="event" key={e.seq}>
              <span className="seq">#{e.seq}</span>
              <span className="etype">{e.event_type}</span>
              <span className="actor">{e.actor} · {fmt(e.created_at)}</span>
              <span className="hash">{e.this_hash.slice(0, 12)}…</span>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
