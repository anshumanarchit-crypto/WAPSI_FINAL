-- ==============================================================================
-- WAPSI MIGRATION 12: Harden Opt-Out and Customer Interactions RLS Policies
-- Sequence: 20261104000012_harden_opt_out_and_interactions_rls.sql
-- Status: REVIEW ONLY — DO NOT EXECUTE AUTOMATICALLY ON HOSTED SUPABASE
-- Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, PostgreSQL 17.11)
--
-- Security Audit Findings:
-- In Migration 20261101000005, policies for opt_out_registry, customer_interactions,
-- and opt_out_audit_trail granted full access `TO authenticated, wapsi_app`.
-- The `authenticated` role encompasses any authenticated tenant user or frontend JWT.
-- Granting direct SELECT/INSERT/UPDATE/DELETE on these global tables to `authenticated`
-- exposes customer phone numbers and interaction history across all merchants,
-- violating tenant data confidentiality and DPDP 2023 pseudonymization principles.
--
-- Remediation Plan (Non-Destructive):
-- 1. Preserve statutory global opt-out semantics across all merchants (DPDP 2023 & Meta policy).
--    Do NOT partition or namespace opt_out_registry by merchant_id, because opt-outs
--    are an absolute customer right across the entire recovery platform.
-- 2. Revoke direct table access from `authenticated` role for all three governance tables.
-- 3. Scope RLS policies exclusively to trusted backend execution roles (`wapsi_app`, `service_role`).
-- 4. Expose a narrow, rate-limited SECURITY DEFINER boolean query function for checking
--    single-phone opt-out status without leaking table records.
-- ==============================================================================

-- 1. Restrict opt_out_registry RLS to trusted backend service roles
DROP POLICY IF EXISTS p_opt_out_registry_all ON public.opt_out_registry;
DROP POLICY IF EXISTS p_opt_out_registry_backend ON public.opt_out_registry;

CREATE POLICY p_opt_out_registry_backend ON public.opt_out_registry
    FOR ALL TO wapsi_app, service_role
    USING (true)
    WITH CHECK (true);

-- Revoke direct permissions from public, anon, and authenticated
REVOKE ALL ON TABLE public.opt_out_registry FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.opt_out_registry TO wapsi_app, service_role;


-- 2. Restrict customer_interactions RLS to trusted backend service roles
DROP POLICY IF EXISTS p_customer_interactions_all ON public.customer_interactions;
DROP POLICY IF EXISTS p_customer_interactions_backend ON public.customer_interactions;

CREATE POLICY p_customer_interactions_backend ON public.customer_interactions
    FOR ALL TO wapsi_app, service_role
    USING (true)
    WITH CHECK (true);

-- Revoke direct permissions from public, anon, and authenticated
REVOKE ALL ON TABLE public.customer_interactions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.customer_interactions TO wapsi_app, service_role;


-- 3. Restrict opt_out_audit_trail RLS to trusted backend service roles
DROP POLICY IF EXISTS p_opt_out_audit_trail_select ON public.opt_out_audit_trail;
DROP POLICY IF EXISTS p_opt_out_audit_trail_insert ON public.opt_out_audit_trail;
DROP POLICY IF EXISTS p_opt_out_audit_trail_backend_select ON public.opt_out_audit_trail;
DROP POLICY IF EXISTS p_opt_out_audit_trail_backend_insert ON public.opt_out_audit_trail;

CREATE POLICY p_opt_out_audit_trail_backend_select ON public.opt_out_audit_trail
    FOR SELECT TO wapsi_app, service_role
    USING (true);

CREATE POLICY p_opt_out_audit_trail_backend_insert ON public.opt_out_audit_trail
    FOR INSERT TO wapsi_app, service_role
    WITH CHECK (true);

-- Revoke direct permissions from public, anon, and authenticated
REVOKE ALL ON TABLE public.opt_out_audit_trail FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE public.opt_out_audit_trail TO wapsi_app, service_role;


-- 4. Privacy-Preserving SECURITY DEFINER Function for Phone Opt-Out Lookup
-- Enables verification without exposing bulk customer phone numbers
CREATE OR REPLACE FUNCTION public.check_phone_opt_out_status(p_phone text)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF p_phone IS NULL OR pg_catalog.length(p_phone) < 8 THEN
        RETURN FALSE;
    END IF;

    RETURN EXISTS (
        SELECT 1
        FROM public.opt_out_registry
        WHERE phone = p_phone
          AND is_active = TRUE
    );
END;
$$;

ALTER FUNCTION public.check_phone_opt_out_status(text) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.check_phone_opt_out_status(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.check_phone_opt_out_status(text) TO authenticated, wapsi_app, service_role;
