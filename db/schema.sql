-- Warden ledger schema (reference).
--
-- Tables (proposals, approvals, standing_rules, audit_log) are created from the
-- SQLAlchemy models in services/common/warden_common/models.py via create_all()
-- at service startup. They are documented here for review.
--
-- The append-only trigger below is the part worth reading: it makes the audit
-- trail immutable at the database layer, not just by application convention.
-- It is applied automatically by warden_common.db.apply_postgres_hardening().

-- proposals     (id, capability, subject, requested_by, payload jsonb,
--                payload_hash, status, slack_channel, slack_message_ts, created_at)
-- approvals     (id, proposal_id, approver, decision, approval_token,
--                payload_hash, expires_at, consumed_at, created_at)
-- standing_rules(id, subject, action_type, created_by, active, created_at)
-- audit_log     (seq PK, event_type, actor, proposal_id, approval_id,
--                payload jsonb, prev_hash, this_hash, created_at)
--
-- 'capability' records which agent capability produced a proposal (e.g.
-- "triage"); 'subject' is the scope it ran against (e.g. a repo). Both are
-- capability-agnostic so one ledger serves every capability.

-- ---------------------------------------------------------------------------
-- Append-only enforcement: reject any attempt to UPDATE/DELETE/TRUNCATE audit.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION warden_block_audit_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % rejected', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS warden_audit_append_only ON audit_log;
CREATE TRIGGER warden_audit_append_only
BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log
FOR EACH STATEMENT EXECUTE FUNCTION warden_block_audit_mutation();
