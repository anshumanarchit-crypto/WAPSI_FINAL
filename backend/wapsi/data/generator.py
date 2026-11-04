"""
Synthetic Data Generator with Known Potential Outcomes (Ground Truth Causal DGP).
Generates realistic Razorpay payment failure datasets with known treatment effects (ITE),
observational selection bias, confounders, and survival recovery delays.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
from wapsi.core.taxonomy import RecoveryAction, ErrorCategory, PaymentMethod


class SyntheticRecoveryDataGenerator:
    """
    Generates synthetic payment failure data with explicit Potential Outcomes Y(a)
    for all candidate actions a in RecoveryAction.
    
    This enables exact mathematical evaluation of causal metrics (AUUC, Qini, ITE error)
    against known ground truth.
    """

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        self.rng = np.random.default_rng(random_seed)
        self.actions = [a.value for a in RecoveryAction]
        self.action_to_idx = {a: i for i, a in enumerate(self.actions)}

    def generate_dataset(
        self,
        n_samples: int = 5000,
        observational_bias: bool = True
    ) -> Tuple[pd.DataFrame, Dict[str, np.ndarray]]:
        """
        Generates synthetic failure dataset.
        
        Returns:
            df: DataFrame of observed covariates X, assigned action A, observed outcome Y_obs,
                and observed recovery delay T_obs.
            potential_outcomes: Dict containing:
                - 'Y_potential': array of shape (n_samples, n_actions) of binary recovery outcomes
                - 'prob_potential': array of shape (n_samples, n_actions) of underlying recovery probabilities
                - 'tau_ground_truth': array of shape (n_samples, n_actions) of true treatment uplift vs NO_ACTION
                - 'timing_potential_sec': array of shape (n_samples, n_actions) of recovery duration in seconds
        """
        rng = self.rng

        # 1. Generate Covariates (X)
        user_ids = [f"usr_{rng.integers(100000, 999999)}" for _ in range(n_samples)]
        payment_ids = [f"pay_{rng.integers(1000000, 9999999):x}" for _ in range(n_samples)]
        merchant_ids = [f"merch_{rng.choice(['retail_hub', 'cloud_saas', 'fashion_direct', 'fintech_flow', 'edtech_prime'])}" for _ in range(n_samples)]
        
        # Amount in INR (log-normal distribution)
        amount_in_inr = np.round(np.exp(rng.normal(loc=7.5, scale=1.0, size=n_samples)), 2) # median ~1800 INR
        amount_in_inr = np.clip(amount_in_inr, 99.0, 75000.0)

        # Payment Methods
        pm_choices = [PaymentMethod.UPI.value, PaymentMethod.CARD_CREDIT.value, PaymentMethod.CARD_DEBIT.value, PaymentMethod.NETBANKING.value, PaymentMethod.BNPL.value]
        pm_probs = [0.65, 0.15, 0.10, 0.07, 0.03]
        payment_methods = rng.choice(pm_choices, size=n_samples, p=pm_probs)

        # Device OS & Network
        device_os = rng.choice(["Android", "iOS", "Web_Desktop"], size=n_samples, p=[0.72, 0.18, 0.10])
        network_type = rng.choice(["5G", "4G", "3G", "WiFi", "Broadband"], size=n_samples, p=[0.35, 0.45, 0.05, 0.12, 0.03])
        
        # User history & friction state
        hist_orders = rng.poisson(lam=4.0, size=n_samples)
        hist_recovery_rate = np.clip(rng.beta(a=3, b=5, size=n_samples), 0.0, 1.0)
        retry_attempt_number = rng.choice([1, 2, 3, 4], size=n_samples, p=[0.65, 0.22, 0.09, 0.04])
        hour_of_day = rng.integers(0, 24, size=n_samples)
        is_dnd_window = ((hour_of_day >= 21) | (hour_of_day < 9)).astype(int)

        # Error codes and categories
        error_distribution = {
            # Error Code: (Category, baseline probability weight)
            "UPI_APP_TIMEOUT": (ErrorCategory.FRICTION_OTP_UX.value, 0.30),
            "AUTHENTICATION_FAILED": (ErrorCategory.FRICTION_OTP_UX.value, 0.15),
            "GATEWAY_ERROR": (ErrorCategory.TECHNICAL_GATEWAY.value, 0.15),
            "BANK_DOWNTIME": (ErrorCategory.TECHNICAL_GATEWAY.value, 0.10),
            "INSUFFICIENT_FUNDS": (ErrorCategory.FINANCIAL_BALANCE.value, 0.12),
            "CARD_LIMIT_EXCEEDED": (ErrorCategory.FINANCIAL_BALANCE.value, 0.06),
            "USER_CANCELLED": (ErrorCategory.ABANDONMENT_INTENT.value, 0.08),
            "CART_ABANDONED_ON_CHECKOUT": (ErrorCategory.ABANDONMENT_INTENT.value, 0.04),
        }
        
        err_codes = list(error_distribution.keys())
        err_weights = np.array([error_distribution[k][1] for k in err_codes])
        err_weights = err_weights / err_weights.sum()
        
        chosen_err_indices = rng.choice(len(err_codes), size=n_samples, p=err_weights)
        error_codes = [err_codes[idx] for idx in chosen_err_indices]
        error_categories = [error_distribution[err_codes[idx]][0] for idx in chosen_err_indices]

        # 2. Potential Outcomes Data Generating Process (DGP)
        # We define latent baseline recovery probability p0(x) (Control = NO_ACTION)
        # And latent treatment effects tau_a(x) for each action a
        
        logit_base = (
            -2.0
            + 0.6 * (payment_methods == PaymentMethod.UPI.value)
            - 0.00003 * amount_in_inr
            + 0.8 * hist_recovery_rate
            - 0.3 * (retry_attempt_number - 1)
            + 0.4 * (np.array(error_categories) == ErrorCategory.TECHNICAL_GATEWAY.value) # technical errors sometimes retry on their own
            - 0.6 * (np.array(error_categories) == ErrorCategory.FINANCIAL_BALANCE.value)
        )
        p0 = 1.0 / (1.0 + np.exp(-logit_base))
        p0 = np.clip(p0, 0.02, 0.45) # Organic baseline typically 5% - 30%

        n_actions = len(self.actions)
        prob_potential = np.zeros((n_samples, n_actions))
        prob_potential[:, 0] = p0 # Action 0: NO_ACTION

        # Heterogeneous Treatment Effect formulas:
        for idx, act in enumerate(self.actions):
            if act == RecoveryAction.NO_ACTION.value:
                continue
            
            tau_latent = np.zeros(n_samples)
            
            if act == RecoveryAction.INSTANT_SMART_RETRY.value:
                # Strongest for technical/gateway downtime, zero for financial balance/intent
                is_tech = (np.array(error_categories) == ErrorCategory.TECHNICAL_GATEWAY.value).astype(float)
                is_upi = (payment_methods == PaymentMethod.UPI.value).astype(float)
                tau_latent = 0.45 * is_tech + 0.10 * is_upi - 0.05 * (retry_attempt_number > 2)
            
            elif act == RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value:
                # Strongest for UPI & OTP/Friction, high responsiveness on Android/Mobile
                is_friction = (np.array(error_categories) == ErrorCategory.FRICTION_OTP_UX.value).astype(float)
                is_mobile = (device_os == "Android").astype(float) * 0.15 + (device_os == "iOS").astype(float) * 0.10
                tau_latent = 0.38 * is_friction + is_mobile + 0.15 * hist_recovery_rate - 0.00001 * amount_in_inr
            
            elif act == RecoveryAction.SMS_FALLBACK_LINK.value:
                # Modest uplift across board, slightly better if non-Android or low network
                is_friction = (np.array(error_categories) == ErrorCategory.FRICTION_OTP_UX.value).astype(float)
                is_weak_net = np.isin(network_type, ["3G", "4G"]).astype(float) * 0.08
                tau_latent = 0.18 * is_friction + is_weak_net + 0.05 * hist_recovery_rate
            
            elif act == RecoveryAction.BNPL_ALTERNATIVE_OFFER.value:
                # Highly effective for financial balance & higher ticket cart values (> 1500 INR)
                is_balance = (np.array(error_categories) == ErrorCategory.FINANCIAL_BALANCE.value).astype(float)
                is_mid_high_ticket = ((amount_in_inr >= 1500) & (amount_in_inr <= 25000)).astype(float) * 0.25
                tau_latent = 0.40 * is_balance + is_mid_high_ticket
            
            elif act == RecoveryAction.MERCHANT_DISCOUNT_NUDGE.value:
                # Highly effective for price-sensitive abandonment & user cancellations
                is_abandon = (np.array(error_categories) == ErrorCategory.ABANDONMENT_INTENT.value).astype(float)
                is_modest_ticket = (amount_in_inr <= 5000).astype(float) * 0.15
                tau_latent = 0.35 * is_abandon + is_modest_ticket
            
            elif act == RecoveryAction.CALL_ASSIST_IVR.value:
                # Effective mainly for high-value orders (> 5000 INR) where high-touch reassurance unblocks drop
                is_high_ticket = (amount_in_inr > 5000).astype(float) * 0.32
                is_repeat_fail = (retry_attempt_number >= 2).astype(float) * 0.12
                tau_latent = is_high_ticket + is_repeat_fail - 0.10 * (device_os == "iOS") # iOS users dislike IVR nudges
            
            # Combine baseline + uplift to get potential probability P(Y(a) = 1 | X)
            prob_a = np.clip(p0 + tau_latent, 0.01, 0.95)
            prob_potential[:, idx] = prob_a

        # Generate binary realization Y(a) ~ Bernoulli(prob_a)
        Y_potential = (rng.uniform(size=(n_samples, n_actions)) < prob_potential).astype(int)
        tau_ground_truth = prob_potential - prob_potential[:, [0]] # true ITE probability difference

        # Generate Potential Recovery Latency (Seconds to recover under each action)
        # Fast actions like smart retry recover in seconds; WhatsApp in 1-5 mins; IVR in 5-15 mins
        base_delays_sec = {
            RecoveryAction.NO_ACTION.value: 1200.0,
            RecoveryAction.INSTANT_SMART_RETRY.value: 15.0,
            RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value: 180.0,
            RecoveryAction.SMS_FALLBACK_LINK.value: 360.0,
            RecoveryAction.BNPL_ALTERNATIVE_OFFER.value: 450.0,
            RecoveryAction.MERCHANT_DISCOUNT_NUDGE.value: 600.0,
            RecoveryAction.CALL_ASSIST_IVR.value: 900.0,
        }
        timing_potential_sec = np.zeros((n_samples, n_actions))
        for idx, act in enumerate(self.actions):
            base_t = base_delays_sec[act]
            jitter = rng.exponential(scale=base_t * 0.4, size=n_samples)
            timing_potential_sec[:, idx] = np.round(base_t + jitter, 1)

        # 3. Observational Treatment Assignment (A) with Realistic Policy Bias
        if observational_bias:
            # Historical heuristic: rules assigned actions based on crude heuristics
            assignment_logits = np.zeros((n_samples, n_actions))
            assignment_logits[:, 0] = 0.5 # NO_ACTION baseline
            assignment_logits[:, 1] = 1.2 * (np.array(error_categories) == ErrorCategory.TECHNICAL_GATEWAY.value)
            assignment_logits[:, 2] = 1.0 * (payment_methods == PaymentMethod.UPI.value)
            assignment_logits[:, 3] = 0.4
            assignment_logits[:, 4] = 0.8 * (np.array(error_categories) == ErrorCategory.FINANCIAL_BALANCE.value)
            assignment_logits[:, 5] = 0.6 * (np.array(error_categories) == ErrorCategory.ABANDONMENT_INTENT.value)
            assignment_logits[:, 6] = 0.9 * (amount_in_inr > 5000)
            
            exp_logits = np.exp(assignment_logits - np.max(assignment_logits, axis=1, keepdims=True))
            propensities = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
            
            assigned_action_indices = [
                rng.choice(n_actions, p=propensities[i]) for i in range(n_samples)
            ]
        else:
            # Randomized Controlled Trial (RCT) uniform exploration
            assigned_action_indices = rng.integers(0, n_actions, size=n_samples)

        assigned_actions = [self.actions[idx] for idx in assigned_action_indices]
        
        # 4. SUTVA: Observed outcome Y_obs = Y(A)
        row_indices = np.arange(n_samples)
        Y_obs = Y_potential[row_indices, assigned_action_indices]
        T_obs_sec = timing_potential_sec[row_indices, assigned_action_indices]

        # Assemble DataFrame
        df = pd.DataFrame({
            "payment_id": payment_ids,
            "user_id": user_ids,
            "merchant_id": merchant_ids,
            "amount_in_inr": amount_in_inr,
            "payment_method": payment_methods,
            "error_code": error_codes,
            "error_category": error_categories,
            "user_device_os": device_os,
            "user_network_type": network_type,
            "historical_orders_count": hist_orders,
            "historical_recovery_rate": np.round(hist_recovery_rate, 4),
            "retry_attempt_number": retry_attempt_number,
            "hour_of_day": hour_of_day,
            "is_dnd_window": is_dnd_window,
            "assigned_action": assigned_actions,
            "assigned_action_idx": assigned_action_indices,
            "recovered": Y_obs,
            "recovery_delay_sec": T_obs_sec
        })

        potential_outcomes = {
            "Y_potential": Y_potential,
            "prob_potential": prob_potential,
            "tau_ground_truth": tau_ground_truth,
            "timing_potential_sec": timing_potential_sec,
            "action_names": self.actions
        }

        return df, potential_outcomes
