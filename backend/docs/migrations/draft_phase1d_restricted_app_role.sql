-- ==============================================================================
-- WAPSI PHASE 1D.2: RESTRICTED APPLICATION RUNTIME ROLE & LEAST-PRIVILEGE GRANTS
-- DRAFT REVIEW ONLY — DO NOT EXECUTE DIRECTLY ON HOSTED CLUSTER
-- Location: docs/migrations/draft_phase1d_restricted_app_role.sql
-- Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, PostgreSQL 17.11)
-- ==============================================================================

-- 1. Create Restricted Application Login Role
-- (Password must be provisioned via secure vault/CLI out-of-band; never committed to Git)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'wapsi_app') THEN
        CREATE ROLE wapsi_app WITH
            LOGIN
            NOBYPASSRLS
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT;
    END IF;
END
$$;

-- 2. Schema Usage Privilege (Explicitly Revoke Create)
REVOKE CREATE ON SCHEMA public FROM wapsi_app;
GRANT USAGE ON SCHEMA public TO wapsi_app;

-- 3. Table-by-Table Least-Privilege DML Grants (ZERO DELETE GRANTS ACROSS ALL 15 TABLES)
GRANT SELECT ON public.merchants TO wapsi_app;
GRANT SELECT ON public.merchant_configurations TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.customers TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.transactions TO wapsi_app;
GRANT SELECT ON public.model_versions TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.causal_decisions TO wapsi_app;
GRANT SELECT, INSERT ON public.webhook_inbox TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.idempotency_keys TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.recovery_outbox TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.recovery_dispatches TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.payment_outcomes TO wapsi_app;
GRANT SELECT, INSERT ON public.audit_ledger_blocks TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.bandit_weights TO wapsi_app;

-- Tables public.merchant_api_keys and public.merchant_memberships have ZERO DML grants to wapsi_app.
-- Sequences in public schema: Exactly 0 sequences exist in deployed catalog. Zero sequence grants required.

-- 4. Secure API-Key Authentication Lookup Function
-- Hardened: search_path = '', fully qualified objects, strict SHA-256 regex, minimal return tuple
CREATE OR REPLACE FUNCTION public.lookup_merchant_by_api_key_hash(p_hashed_key text)
RETURNS TABLE (
    merchant_id uuid,
    merchant_code character varying,
    merchant_status character varying,
    key_scopes jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    -- Strict input validation: SHA-256 hex string (exactly 64 hex characters)
    IF p_hashed_key IS NULL 
       OR pg_catalog.length(p_hashed_key) != 64 
       OR p_hashed_key !~ '^[0-9a-f]{64}$' THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT 
        k.merchant_id,
        m.merchant_id AS merchant_code,
        m.status AS merchant_status,
        k.scopes::jsonb AS key_scopes
    FROM public.merchant_api_keys k
    JOIN public.merchants m ON m.id = k.merchant_id
    WHERE k.hashed_key = p_hashed_key
      AND k.is_revoked = false
      AND (k.expires_at IS NULL OR k.expires_at > pg_catalog.now())
      AND m.status = 'ACTIVE';
END;
$$;

-- Function Execution Permissions (Explicit Revocation and Reviewed Allowlist)
REVOKE ALL ON FUNCTION public.lookup_merchant_by_api_key_hash(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lookup_merchant_by_api_key_hash(text) TO wapsi_app, service_role;

GRANT EXECUTE ON FUNCTION public.current_active_merchant_id() TO wapsi_app;
GRANT EXECUTE ON FUNCTION public.has_merchant_role(uuid, text[]) TO wapsi_app;
GRANT EXECUTE ON FUNCTION public.update_dispatch_delivery_status(character varying, character varying, character varying) TO wapsi_app;
-- Note: public.prevent_audit_ledger_tampering() is a TRIGGER function; direct EXECUTE is strictly withheld.

-- 5. RLS Policy Retargeting & Corrections (Retarget to include wapsi_app)

-- Merchants (Read-only for wapsi_app)
DROP POLICY IF EXISTS p_merchants_select ON public.merchants;
CREATE POLICY p_merchants_select ON public.merchants
    FOR SELECT TO authenticated, wapsi_app
    USING (
        id = public.current_active_merchant_id()
        AND public.has_merchant_role(id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

-- Model Versions (Global read for wapsi_app)
DROP POLICY IF EXISTS p_model_versions_select ON public.model_versions;
CREATE POLICY p_model_versions_select ON public.model_versions
    FOR SELECT TO authenticated, wapsi_app
    USING (true);

-- Transactions (Add system_service to SELECT)
DROP POLICY IF EXISTS p_transactions_select ON public.transactions;
CREATE POLICY p_transactions_select ON public.transactions
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_transactions_insert ON public.transactions;
CREATE POLICY p_transactions_insert ON public.transactions
    FOR INSERT TO authenticated, wapsi_app
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

DROP POLICY IF EXISTS p_transactions_update ON public.transactions;
CREATE POLICY p_transactions_update ON public.transactions
    FOR UPDATE TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

-- Customers (Add system_service to SELECT)
DROP POLICY IF EXISTS p_customers_select ON public.customers;
CREATE POLICY p_customers_select ON public.customers
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_customers_manage ON public.customers;
CREATE POLICY p_customers_manage ON public.customers
    FOR ALL TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );

-- Configurations (Add system_service to SELECT)
DROP POLICY IF EXISTS p_configurations_select ON public.merchant_configurations;
CREATE POLICY p_configurations_select ON public.merchant_configurations
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

-- Causal Decisions (Add system_service to SELECT)
DROP POLICY IF EXISTS p_decisions_select ON public.causal_decisions;
CREATE POLICY p_decisions_select ON public.causal_decisions
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_decisions_insert ON public.causal_decisions;
CREATE POLICY p_decisions_insert ON public.causal_decisions
    FOR INSERT TO authenticated, wapsi_app
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

DROP POLICY IF EXISTS p_decisions_update ON public.causal_decisions;
CREATE POLICY p_decisions_update ON public.causal_decisions
    FOR UPDATE TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

-- Webhook Inbox (Add system_service to SELECT)
DROP POLICY IF EXISTS p_webhook_inbox_select ON public.webhook_inbox;
CREATE POLICY p_webhook_inbox_select ON public.webhook_inbox
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_webhook_inbox_insert ON public.webhook_inbox;
CREATE POLICY p_webhook_inbox_insert ON public.webhook_inbox
    FOR INSERT TO authenticated, wapsi_app
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['system_service'])
    );

-- Idempotency Keys (Retarget to wapsi_app)
DROP POLICY IF EXISTS p_idempotency_select ON public.idempotency_keys;
CREATE POLICY p_idempotency_select ON public.idempotency_keys
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

DROP POLICY IF EXISTS p_idempotency_manage ON public.idempotency_keys;
CREATE POLICY p_idempotency_manage ON public.idempotency_keys
    FOR ALL TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );

-- Recovery Outbox (Add system_service to SELECT)
DROP POLICY IF EXISTS p_outbox_select ON public.recovery_outbox;
CREATE POLICY p_outbox_select ON public.recovery_outbox
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_outbox_manage ON public.recovery_outbox;
CREATE POLICY p_outbox_manage ON public.recovery_outbox
    FOR ALL TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

-- Recovery Dispatches (Add system_service to SELECT)
DROP POLICY IF EXISTS p_dispatches_select ON public.recovery_dispatches;
CREATE POLICY p_dispatches_select ON public.recovery_dispatches
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_dispatches_insert ON public.recovery_dispatches;
CREATE POLICY p_dispatches_insert ON public.recovery_dispatches
    FOR INSERT TO authenticated, wapsi_app
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

DROP POLICY IF EXISTS p_dispatches_update ON public.recovery_dispatches;
CREATE POLICY p_dispatches_update ON public.recovery_dispatches
    FOR UPDATE TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['system_service', 'merchant_admin', 'recovery_operator'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['system_service', 'merchant_admin', 'recovery_operator'])
        AND status IN ('SENT', 'DELIVERED', 'READ', 'FAILED')
    );

-- Payment Outcomes (Add system_service to SELECT)
DROP POLICY IF EXISTS p_outcomes_select ON public.payment_outcomes;
CREATE POLICY p_outcomes_select ON public.payment_outcomes
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_outcomes_manage ON public.payment_outcomes;
CREATE POLICY p_outcomes_manage ON public.payment_outcomes
    FOR ALL TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );

-- Audit Ledger Blocks (Retarget to include wapsi_app)
DROP POLICY IF EXISTS p_audit_blocks_select ON public.audit_ledger_blocks;
CREATE POLICY p_audit_blocks_select ON public.audit_ledger_blocks
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

DROP POLICY IF EXISTS p_audit_blocks_insert ON public.audit_ledger_blocks;
CREATE POLICY p_audit_blocks_insert ON public.audit_ledger_blocks
    FOR INSERT TO authenticated, wapsi_app
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );

-- Bandit Weights (Add system_service to SELECT)
DROP POLICY IF EXISTS p_bandit_weights_select ON public.bandit_weights;
CREATE POLICY p_bandit_weights_select ON public.bandit_weights
    FOR SELECT TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'system_service'])
    );

DROP POLICY IF EXISTS p_bandit_weights_manage ON public.bandit_weights;
CREATE POLICY p_bandit_weights_manage ON public.bandit_weights
    FOR ALL TO authenticated, wapsi_app
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );
