import { Pool, type QueryResultRow } from "pg";
import crypto from "crypto";
import type {
  Action,
  AuditEntry,
  AuditResult,
  ProposalPayload,
  ProposalRow,
  ProposalSummary,
} from "./types";

// The dashboard is READ-ONLY. It connects to the same ledger Postgres the agent
// and runner use, and never issues a write. DATABASE_URL here is a plain
// postgres:// URL (the Python services use the +psycopg variant).
let pool: Pool | undefined;
function getPool(): Pool {
  if (!pool) {
    pool = new Pool({
      connectionString:
        process.env.DATABASE_URL ||
        "postgres://warden:warden@localhost:5432/warden",
    });
  }
  return pool;
}

export async function listProposals(limit = 100): Promise<ProposalSummary[]> {
  const { rows } = await getPool().query<ProposalRow & QueryResultRow>(
    `SELECT id, capability, subject, requested_by, status, payload, created_at
       FROM proposals ORDER BY created_at DESC LIMIT $1`,
    [limit]
  );
  return rows.map((r) => ({
    id: r.id,
    capability: r.capability,
    subject: r.subject,
    requested_by: r.requested_by,
    status: r.status,
    counts: countActions(r.payload),
    created_at: r.created_at,
  }));
}

export async function getProposal(id: string): Promise<ProposalRow | null> {
  const { rows } = await getPool().query<ProposalRow & QueryResultRow>(
    `SELECT id, capability, subject, requested_by, status, payload, payload_hash, created_at
       FROM proposals WHERE id = $1`,
    [id]
  );
  return rows[0] || null;
}

export async function listAudit(limit = 500): Promise<AuditResult> {
  const { rows } = await getPool().query<AuditEntry & QueryResultRow>(
    `SELECT seq, event_type, actor, proposal_id, approval_id, payload,
            prev_hash, this_hash, created_at
       FROM audit_log ORDER BY seq ASC LIMIT $1`,
    [limit]
  );
  const { ok, firstBad } = verifyChain(rows);
  return { entries: rows, chainOk: ok, firstBadSeq: firstBad };
}

// Mirror of warden_common.crypto so the dashboard can independently re-verify
// the hash chain it renders — "verified", not "trust me".
function canonical(obj: unknown): string {
  if (obj === null || typeof obj !== "object") return JSON.stringify(obj);
  if (Array.isArray(obj)) return "[" + obj.map(canonical).join(",") + "]";
  const record = obj as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return (
    "{" +
    keys.map((k) => JSON.stringify(k) + ":" + canonical(record[k])).join(",") +
    "}"
  );
}

function chainHash(prev: string, payload: unknown): string {
  return crypto
    .createHash("sha256")
    .update(prev + "\n" + canonical(payload))
    .digest("hex");
}

function verifyChain(rows: AuditEntry[]): { ok: boolean; firstBad: number | null } {
  let prev = "0".repeat(64);
  for (const r of rows) {
    const payload = {
      event_type: r.event_type,
      actor: r.actor,
      proposal_id: r.proposal_id,
      approval_id: r.approval_id,
      payload: r.payload,
    };
    const expected = chainHash(prev, payload);
    if (expected !== r.this_hash || r.prev_hash !== prev) {
      return { ok: false, firstBad: r.seq };
    }
    prev = r.this_hash;
  }
  return { ok: true, firstBad: null };
}

function countActions(payload: ProposalPayload | null): Record<string, number> {
  // Capability-agnostic: count by action type, whatever those types are.
  const out: Record<string, number> = {};
  for (const a of (payload && payload.actions) || ([] as Action[])) {
    out[a.type] = (out[a.type] || 0) + 1;
  }
  return out;
}
