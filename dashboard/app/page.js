import { listProposals, listAudit } from "./lib/db";

export const dynamic = "force-dynamic"; // always read live ledger state

function fmt(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function fmtCounts(counts) {
  const entries = Object.entries(counts || {});
  if (entries.length === 0) return "—";
  return entries.map(([t, n]) => `${n} ${t}`).join(" · ");
}

function etypeClass(e) {
  if (e.includes("refused") || e.includes("denied")) return "refused";
  if (e.includes("executed")) return "executed";
  if (e.includes("approved")) return "approved";
  if (e.includes("auto")) return "auto";
  return "";
}

export default async function Home() {
  let proposals = [];
  let audit = { entries: [], chainOk: true, firstBadSeq: null };
  let error = null;
  try {
    [proposals, audit] = await Promise.all([listProposals(), listAudit()]);
  } catch (e) {
    error = e.message;
  }

  return (
    <main className="wrap">
      <div className="brand">
        <h1>WARDEN</h1>
        <span className="tag">permission ledger · immutable audit trail</span>
      </div>
      <p className="sub">
        Every consequential action a capability proposes is routed through a human approval
        and executed by a separate, write-scoped runner. This ledger is the first-class record
        of who asked, what was proposed, who approved, what ran, and when — hash-chained so
        tampering is visible. Triage is the first capability; the ledger serves them all.
      </p>

      {error && (
        <div className="panel" style={{ padding: 16, color: "var(--warn)" }}>
          Could not reach the ledger ({error}). Is Postgres up and DATABASE_URL set?
        </div>
      )}

      <div className="grid">
        <section className="panel">
          <h2>Proposals</h2>
          <table>
            <thead>
              <tr>
                <th>Proposal</th><th>Capability</th><th>Subject</th><th>Requested by</th>
                <th>Actions</th><th>Status</th><th>Created</th>
              </tr>
            </thead>
            <tbody>
              {proposals.length === 0 && (
                <tr><td colSpan={7} className="mono">No proposals yet. Run a capability in Slack.</td></tr>
              )}
              {proposals.map((p) => (
                <tr key={p.id}>
                  <td><a href={`/proposal/${p.id}`}>{p.id.slice(0, 8)}</a></td>
                  <td><span className="badge">{p.capability || "—"}</span></td>
                  <td>{p.subject}</td>
                  <td className="mono">{p.requested_by}</td>
                  <td className="pill">{fmtCounts(p.counts)}</td>
                  <td><span className={`badge ${p.status}`}>{p.status}</span></td>
                  <td className="mono">{fmt(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>Audit trail</h2>
          <div className="chainbar">
            <span className={`dot ${audit.chainOk ? "ok" : "bad"}`} />
            <span>
              {audit.chainOk
                ? `Hash chain verified · ${audit.entries.length} entries`
                : `CHAIN BROKEN at seq ${audit.firstBadSeq} — tampering detected`}
            </span>
          </div>
          {audit.entries.map((e) => (
            <div className="event" key={e.seq}>
              <span className="seq">#{e.seq}</span>
              <span className={`etype ${etypeClass(e.event_type)}`}>{e.event_type}</span>
              <span className="actor">
                {e.actor}
                {e.proposal_id ? ` · ${String(e.proposal_id).slice(0, 8)}` : ""}
              </span>
              <span className="hash" title={`prev ${e.prev_hash}`}>
                {e.this_hash.slice(0, 12)}…
              </span>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
