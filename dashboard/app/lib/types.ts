// Domain types for the Warden permission ledger, mirroring the Postgres schema
// (db/schema.sql) and the row shapes the dashboard reads. The dashboard is
// READ-ONLY, so these describe what comes *out* of the ledger, never what goes in.

/** A single consequential action a capability proposes (an entry in payload.actions). */
export interface Action {
  type: string;
  target?: string;
  value?: string;
  provider?: string;
  rationale?: string;
  evidence?: string;
}

/** The JSON payload stored on a proposal row. */
export interface ProposalPayload {
  actions?: Action[];
}

/** A proposals row as returned by getProposal(). created_at is a pg Date. */
export interface ProposalRow {
  id: string;
  capability: string | null;
  subject: string;
  requested_by: string;
  status: string;
  payload: ProposalPayload | null;
  payload_hash: string;
  created_at: Date | string;
}

/** A proposal summarised for the list view, with actions rolled up into counts. */
export interface ProposalSummary {
  id: string;
  capability: string | null;
  subject: string;
  requested_by: string;
  status: string;
  counts: Record<string, number>;
  created_at: Date | string;
}

/** An audit_log row. The hash chain links each entry to its predecessor. */
export interface AuditEntry {
  seq: number;
  event_type: string;
  actor: string;
  proposal_id: string | null;
  approval_id: string | null;
  payload: unknown;
  prev_hash: string;
  this_hash: string;
  created_at: Date | string;
}

/** Result of reading the audit trail plus an independent chain re-verification. */
export interface AuditResult {
  entries: AuditEntry[];
  chainOk: boolean;
  firstBadSeq: number | null;
}
