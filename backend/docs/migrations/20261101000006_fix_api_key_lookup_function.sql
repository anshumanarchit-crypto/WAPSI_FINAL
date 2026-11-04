-- ==============================================================================
-- WAPSI — Migration 20261101000006: Fix API-Key Lookup Function Column Reference
-- Target: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb)
-- Forward-Fix: Corrects m.merchant_id -> m.merchant_code in public.lookup_merchant_by_api_key_hash
-- Schema Alignment:
--   - public.merchants: primary key is 'id' (UUID), external identifier is 'merchant_code' (VARCHAR(64))
--   - public.merchant_api_keys: foreign key 'merchant_id' references public.merchants(id)
-- Security: Preserves SECURITY DEFINER, SET search_path = '', strict SHA-256 validation,
--           read-only execution, and least-privilege EXECUTE grants to wapsi_app & service_role.
-- ==============================================================================

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
        m.merchant_code AS merchant_code,
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

-- Explicitly enforce function ownership and least-privilege execution permissions
ALTER FUNCTION public.lookup_merchant_by_api_key_hash(text) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.lookup_merchant_by_api_key_hash(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lookup_merchant_by_api_key_hash(text) TO wapsi_app, service_role;

