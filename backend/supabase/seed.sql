-- WAPSI Development & Testing Seed Fixtures (supabase/seed.sql)
-- Target: WAPSI-DEV-MUMBAI (Region: ap-south-1)
-- Safe, deterministic initial fixtures for local integration testing & staging.
-- Loaded automatically by `supabase db reset` or selectively applied in development.
-- NEVER executed during production `supabase db push` migrations.

-- 1. Insert Default Test Merchant
INSERT INTO public.merchants (
    id,
    merchant_code,
    name,
    business_type,
    industry,
    website,
    registered_email,
    country,
    currency,
    timezone,
    status
) VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'MRC_928374',
    'Acme Global Technologies',
    'Enterprise SaaS & Subscriptions',
    'FinTech / Ecommerce',
    'https://acmeglobal.io',
    'compliance@acmeglobal.io',
    'India',
    'INR',
    'Asia/Kolkata',
    'ACTIVE'
) ON CONFLICT (merchant_code) DO NOTHING;

-- 2. Insert Default Test Merchant Configuration
INSERT INTO public.merchant_configurations (
    merchant_id,
    recovery_enabled_percent,
    confidence_threshold_percent,
    min_uplift_threshold_percent,
    retry_attempt_limit,
    contact_budget_per_customer,
    recovery_window_start_hour,
    recovery_window_end_hour,
    min_ivr_amount_paise,
    default_merchant_margin_basis_points,
    disallowed_actions,
    channel_settings,
    alert_preferences
) VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    84,
    80,
    12,
    3,
    2,
    9,
    21,
    150000, -- ₹1,500.00
    2000,   -- 20.00%
    '[]'::jsonb,
    '{"whatsapp": true, "sms": true, "email": true, "inApp": true}'::jsonb,
    '{"criticalAlerts": true, "recoveryUpdates": true, "dailySummary": true, "policyViolations": true}'::jsonb
) ON CONFLICT (merchant_id) DO NOTHING;

-- 3. Insert Production Model Version Record
INSERT INTO public.model_versions (
    id,
    model_name,
    version,
    artifact_filename,
    artifact_hash_sha256,
    model_type,
    training_rows,
    conformal_coverage_level,
    is_active_production,
    metrics
) VALUES (
    '10000000-0000-0000-0000-000000000001'::uuid,
    'wapsi_t_learner',
    'v1.0.0',
    'wapsi_t_learner_v1.0.0.joblib',
    '73d7437e5885a08c028a39d89bb62a5e89d1b6e4e5f7a0123456789abcdef012',
    'MultiActionTLearner',
    35000,
    '90% Nominal Coverage (Finite-Sample Valid)',
    true,
    '{"val_auc": 0.8271, "val_log_loss": 0.4735}'::jsonb
) ON CONFLICT (model_name, version) DO NOTHING;

-- 4. Insert Initial Genesis Block into Cryptographic Audit Ledger
INSERT INTO public.audit_ledger_blocks (
    id,
    merchant_id,
    block_index,
    previous_hash,
    block_hash,
    event_type,
    data_payload,
    timestamp
) VALUES (
    '20000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    0,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'GENESIS_BLOCK',
    '{"system": "wapsi-causal-decision-engine", "status": "BOOTSTRAP_COMPLETE", "enclave": "ATTESTED"}'::jsonb,
    now()
) ON CONFLICT (merchant_id, block_index) DO NOTHING;
