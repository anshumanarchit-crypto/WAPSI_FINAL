-- WAPSI Migration 3: Multi-Tenant Row-Level Security (RLS) & Cryptographic Immutability
-- Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, Region: ap-south-1)
-- Architecture: Decoupled Tenant Authorization, Pinned search_path, Secure Dispatch Lifecycle, Strict Audit Ledger
-- Security Hardened: Fail-Closed Identity Resolution, Explicit Role Constraints, Zero Null-Tenant Leakage

-- ==============================================================================
-- 1. SECURITY HELPER FUNCTIONS (search_path Pinned to public)
-- ==============================================================================

-- Resolves the active merchant context from trusted backend session context or trusted Supabase app_metadata JWT claims.
-- NEVER inspects user_metadata (which is user-editable and untrusted).
-- Cross-validates merchant membership and ACTIVE tenant status before returning context.
CREATE OR REPLACE FUNCTION public.current_active_merchant_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_raw text;
    v_merchant_id uuid;
BEGIN
    -- 1. Check trusted backend session context (e.g. SQLAlchemy connection via FastAPI backend)
    v_raw := current_setting('app.current_merchant_id', true);

    -- 2. Check trusted Supabase app_metadata JWT claims (Managed strictly by Server-side Auth Hooks / Admin API)
    IF v_raw IS NULL OR v_raw = '' THEN
        v_raw := (auth.jwt() -> 'app_metadata') ->> 'merchant_id';
    END IF;

    -- Fail-closed if no tenant context is provided
    IF v_raw IS NULL OR v_raw = '' THEN
        RETURN NULL;
    END IF;

    -- Safely cast to UUID; malformed strings fail-closed
    BEGIN
        v_merchant_id := v_raw::uuid;
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;

    -- 3. Membership Validation: If caller is an authenticated user (auth.uid() IS NOT NULL),
    -- verify that user holds an active membership for this merchant and the merchant is ACTIVE.
    IF auth.uid() IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1
            FROM public.merchant_memberships mm
            JOIN public.merchants m ON m.id = mm.merchant_id
            WHERE mm.merchant_id = v_merchant_id
              AND mm.user_id = auth.uid()
              AND mm.is_active = true
              AND m.status = 'ACTIVE'
        ) THEN
            RETURN NULL; -- Inactive or non-member: fail closed!
        END IF;
    ELSE
        -- If called by trusted backend connection without auth.uid(), verify merchant exists and is ACTIVE
        IF NOT EXISTS (
            SELECT 1 FROM public.merchants m
            WHERE m.id = v_merchant_id AND m.status = 'ACTIVE'
        ) THEN
            RETURN NULL; -- Inactive or non-existent merchant: fail closed!
        END IF;
    END IF;

    RETURN v_merchant_id;
END;
$$;

-- Validates whether caller has an active membership for target merchant with allowed roles
CREATE OR REPLACE FUNCTION public.has_merchant_role(target_merchant_id uuid, required_roles text[])
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF target_merchant_id IS NULL THEN
        RETURN false;
    END IF;

    -- If caller is a trusted service connection without auth.uid(),
    -- allow if 'system_service' is in the required roles.
    IF auth.uid() IS NULL THEN
        RETURN 'system_service' = ANY(required_roles);
    END IF;

    RETURN EXISTS (
        SELECT 1
        FROM public.merchant_memberships mm
        JOIN public.merchants m ON m.id = mm.merchant_id
        WHERE mm.merchant_id = target_merchant_id
          AND mm.user_id = auth.uid()
          AND mm.is_active = true
          AND m.status = 'ACTIVE'
          AND mm.role = ANY(required_roles)
    );
END;
$$;


-- ==============================================================================
-- 2. ENABLE ROW-LEVEL SECURITY (All 15 Entities Enforced)
-- ==============================================================================
ALTER TABLE public.merchants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.merchant_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.merchant_configurations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.merchant_api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.causal_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhook_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.idempotency_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recovery_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recovery_dispatches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_ledger_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bandit_weights ENABLE ROW LEVEL SECURITY;


-- ==============================================================================
-- 3. RLS POLICIES: MERCHANTS & MEMBERSHIPS
-- ==============================================================================

-- Merchants: Visible to active members
CREATE POLICY p_merchants_select ON public.merchants
    FOR SELECT
    TO authenticated
    USING (
        id = public.current_active_merchant_id()
        AND public.has_merchant_role(id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service'])
    );

CREATE POLICY p_merchants_update ON public.merchants
    FOR UPDATE
    TO authenticated
    USING (
        id = public.current_active_merchant_id()
        AND public.has_merchant_role(id, ARRAY['merchant_admin'])
    )
    WITH CHECK (
        id = public.current_active_merchant_id()
        AND public.has_merchant_role(id, ARRAY['merchant_admin'])
    );

-- Merchant Memberships: User can view their own memberships; Admin can view all for active merchant
CREATE POLICY p_memberships_select ON public.merchant_memberships
    FOR SELECT
    TO authenticated
    USING (
        user_id = auth.uid()
        OR (
            merchant_id = public.current_active_merchant_id()
            AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
        )
    );

CREATE POLICY p_memberships_admin_manage ON public.merchant_memberships
    FOR ALL
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
    );


-- ==============================================================================
-- 4. RLS POLICIES: CONFIGURATIONS & API KEYS
-- ==============================================================================

CREATE POLICY p_configurations_select ON public.merchant_configurations
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor'])
    );

CREATE POLICY p_configurations_update ON public.merchant_configurations
    FOR UPDATE
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
    );

-- API Keys: Only Admin can view and manage
CREATE POLICY p_api_keys_select ON public.merchant_api_keys
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
    );

CREATE POLICY p_api_keys_admin_manage ON public.merchant_api_keys
    FOR ALL
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin'])
    );


-- ==============================================================================
-- 5. RLS POLICIES: CUSTOMERS & TRANSACTIONS
-- ==============================================================================

CREATE POLICY p_customers_select ON public.customers
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor'])
    );

CREATE POLICY p_customers_manage ON public.customers
    FOR ALL
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );

-- Transactions: Selectable by tenant team; inserted by authorized staff / service
CREATE POLICY p_transactions_select ON public.transactions
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor'])
    );

CREATE POLICY p_transactions_insert ON public.transactions
    FOR INSERT
    TO authenticated
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

CREATE POLICY p_transactions_update ON public.transactions
    FOR UPDATE
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );


-- ==============================================================================
-- 6. RLS POLICIES: MODEL VERSIONS (Global Read, System Manage)
-- ==============================================================================

CREATE POLICY p_model_versions_select ON public.model_versions
    FOR SELECT
    TO authenticated
    USING (true); -- Publicly viewable by all authenticated operators


-- ==============================================================================
-- 7. RLS POLICIES: CAUSAL DECISIONS
-- ==============================================================================

CREATE POLICY p_decisions_select ON public.causal_decisions
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor'])
    );

CREATE POLICY p_decisions_insert ON public.causal_decisions
    FOR INSERT
    TO authenticated
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

CREATE POLICY p_decisions_update ON public.causal_decisions
    FOR UPDATE
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );


-- ==============================================================================
-- 8. RLS POLICIES: WEBHOOK INBOX & IDEMPOTENCY
-- ==============================================================================

-- Select: Tenant team can inspect only their own merchant's webhooks.
-- Unassigned webhooks (merchant_id IS NULL) are NEVER exposed to ordinary merchants.
CREATE POLICY p_webhook_inbox_select ON public.webhook_inbox
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'auditor'])
    );

-- Insert: Only trusted backend service (system_service) can insert into webhook_inbox after HMAC verification.
-- Ordinary users and public clients CANNOT insert raw webhooks.
CREATE POLICY p_webhook_inbox_insert ON public.webhook_inbox
    FOR INSERT
    TO authenticated
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['system_service'])
    );

CREATE POLICY p_idempotency_select ON public.idempotency_keys
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

CREATE POLICY p_idempotency_manage ON public.idempotency_keys
    FOR ALL
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );


-- ==============================================================================
-- 9. RLS POLICIES: RECOVERY OUTBOX & DISPATCHES
-- ==============================================================================

CREATE POLICY p_outbox_select ON public.recovery_outbox
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'auditor'])
    );

CREATE POLICY p_outbox_manage ON public.recovery_outbox
    FOR ALL
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

CREATE POLICY p_dispatches_select ON public.recovery_dispatches
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor'])
    );

CREATE POLICY p_dispatches_insert ON public.recovery_dispatches
    FOR INSERT
    TO authenticated
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'system_service'])
    );

-- Updates: Constrained strictly to delivery status transitions ('SENT', 'DELIVERED', 'READ', 'FAILED')
CREATE POLICY p_dispatches_update ON public.recovery_dispatches
    FOR UPDATE
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['system_service', 'merchant_admin', 'recovery_operator'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['system_service', 'merchant_admin', 'recovery_operator'])
        AND status IN ('SENT', 'DELIVERED', 'READ', 'FAILED')
    );

-- Secure Delivery Status Transition Function (Narrowly Scoped)
CREATE OR REPLACE FUNCTION public.update_dispatch_delivery_status(
    p_dispatch_id varchar,
    p_new_status varchar,
    p_provider_message_id varchar DEFAULT NULL
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_merchant_id uuid;
BEGIN
    v_merchant_id := public.current_active_merchant_id();
    IF v_merchant_id IS NULL THEN
        RETURN false;
    END IF;

    IF NOT public.has_merchant_role(v_merchant_id, ARRAY['system_service', 'merchant_admin', 'recovery_operator']) THEN
        RETURN false;
    END IF;

    IF p_new_status NOT IN ('SENT', 'DELIVERED', 'READ', 'FAILED') THEN
        RAISE EXCEPTION 'Invalid recovery dispatch status: %', p_new_status;
    END IF;

    UPDATE public.recovery_dispatches
    SET status = p_new_status,
        provider_message_id = COALESCE(p_provider_message_id, provider_message_id)
    WHERE dispatch_id = p_dispatch_id
      AND merchant_id = v_merchant_id;

    RETURN FOUND;
END;
$$;


-- ==============================================================================
-- 10. RLS POLICIES: PAYMENT OUTCOMES
-- ==============================================================================

CREATE POLICY p_outcomes_select ON public.payment_outcomes
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor'])
    );

CREATE POLICY p_outcomes_manage ON public.payment_outcomes
    FOR ALL
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );


-- ==============================================================================
-- 11. RLS POLICIES: AUDIT LEDGER BLOCKS (Strict Append-Only Immutability)
-- ==============================================================================

-- Select: Tenant team & auditors can inspect their own merchant blocks.
-- Global blocks without merchant_id are accessible only to service_role / system admin.
CREATE POLICY p_audit_blocks_select ON public.audit_ledger_blocks
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer', 'auditor'])
    );

-- Insert: Only Admin / System service can append blocks
CREATE POLICY p_audit_blocks_insert ON public.audit_ledger_blocks
    FOR INSERT
    TO authenticated
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );

-- Update: FORBIDDEN for all roles (Zero updates allowed on cryptographic ledger)
CREATE POLICY p_audit_blocks_update_forbidden ON public.audit_ledger_blocks
    FOR UPDATE
    TO authenticated
    USING (false);

-- Delete: FORBIDDEN for all roles (Zero deletions allowed on cryptographic ledger)
CREATE POLICY p_audit_blocks_delete_forbidden ON public.audit_ledger_blocks
    FOR DELETE
    TO authenticated
    USING (false);

-- Cryptographic Immutability Trigger (Database-Level Tamper Prevention)
-- NOTE ON IMMUTABILITY ARCHITECTURE:
-- This database trigger enforces operational append-only immutability at the application layer.
-- It does not prevent an unrestricted PostgreSQL superuser from issuing DISABLE TRIGGER.
-- Absolute non-repudiation against root database operators is achieved via cryptographic SHA-256
-- hash chaining (where retroactive tampering breaks the mathematical sequence verified by AuditLedger.verify_integrity())
-- and TEE enclave PCR0 measurement attestation.
CREATE OR REPLACE FUNCTION public.prevent_audit_ledger_tampering()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RAISE EXCEPTION 'AuditLedger is an immutable append-only cryptographic ledger. Updates and deletions are strictly forbidden by protocol.';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_ledger_immutability ON public.audit_ledger_blocks;
CREATE TRIGGER trg_audit_ledger_immutability
    BEFORE UPDATE OR DELETE ON public.audit_ledger_blocks
    FOR EACH ROW
    EXECUTE FUNCTION public.prevent_audit_ledger_tampering();


-- ==============================================================================
-- 12. RLS POLICIES: BANDIT WEIGHTS
-- ==============================================================================

CREATE POLICY p_bandit_weights_select ON public.bandit_weights
    FOR SELECT
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'recovery_operator', 'risk_officer'])
    );

CREATE POLICY p_bandit_weights_manage ON public.bandit_weights
    FOR ALL
    TO authenticated
    USING (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    )
    WITH CHECK (
        merchant_id = public.current_active_merchant_id()
        AND public.has_merchant_role(merchant_id, ARRAY['merchant_admin', 'system_service'])
    );


-- ==============================================================================
-- 13. PRIVILEGE & PERMISSION HARDENING (Principle of Least Privilege)
-- ==============================================================================
REVOKE ALL ON FUNCTION public.current_active_merchant_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_active_merchant_id() TO authenticated, service_role;

REVOKE ALL ON FUNCTION public.has_merchant_role(uuid, text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.has_merchant_role(uuid, text[]) TO authenticated, service_role;

REVOKE ALL ON FUNCTION public.update_dispatch_delivery_status(varchar, varchar, varchar) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.update_dispatch_delivery_status(varchar, varchar, varchar) TO authenticated, service_role;

REVOKE ALL ON FUNCTION public.prevent_audit_ledger_tampering() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.prevent_audit_ledger_tampering() TO authenticated, service_role;
