/**
 * Centralized Typed API Client for WAPSI Causal Decision Engine & Operations Gateway.
 * Real data integration connected to FastAPI backend via Vite proxy / direct base URL.
 * Strictly avoids fabricated data in production mode.
 */

export type BackendConnectionStatus = 'LIVE' | 'STARTING' | 'OFFLINE';

export interface HealthStatusResponse {
  status: string;
  service: string;
  version: string;
  models_ready: boolean;
  models_loaded?: boolean;
  database?: {
    status: string;
    connected: boolean;
    dialect: string;
    latency_ms: number;
    is_fallback?: boolean;
  };
  tee_boundary?: {
    enclave_id?: string;
    is_hardware_tee?: boolean;
    mode?: string;
    enclave_measurement_pcr0?: string;
    nonce?: string;
    platform_security_status?: string;
    attestation_signature?: string;
    timestamp?: string;
  };
  audit_ledger_status?: {
    is_valid: boolean;
    total_blocks: number;
    latest_block_hash: string;
  };
}

export interface WorkerHealthResponse {
  status: string;
  worker?: {
    status: string;
    worker_id: string;
    lease_duration_seconds: number;
  };
  queue_depth: number;
  active_leases: number;
  outbox?: {
    PENDING_APPROVAL: number;
    QUEUED: number;
    SENDING: number;
    SENT: number;
    RETRY: number;
    DEAD_LETTER: number;
    RECONCILIATION_REQUIRED: number;
    CANCELLED: number;
    REJECTED: number;
    TOTAL: number;
  };
  timestamp_utc: string;
}

export interface IntegrationsStatusResponse {
  razorpay: {
    mode: string;
    key_id_configured: boolean;
    masked_key_id: string;
    has_key_secret: boolean;
    has_webhook_secret: boolean;
    ready: boolean;
  };
  whatsapp_cloud_api: {
    phone_number_id: string;
    business_account_id: string;
    api_version: string;
    has_access_token: boolean;
    has_verify_token: boolean;
    has_app_secret: boolean;
    configured: boolean;
  };
  database: {
    status: string;
    connected: boolean;
    dialect: string;
    latency_ms: number;
  };
}

export interface ObservationalMetricsResponse {
  status: string;
  metrics: {
    total_observations: number;
    mature_observations: number;
    eligible_dml_records: number;
    eligible_bandit_records: number;
    invalid_propensity_records: number;
    action_distribution: Record<string, number>;
    propensity_summary: Record<string, any>;
    overlap_violation_rate: number;
  };
}

export interface ObservationalExportResponse {
  status: string;
  merchant_id: string;
  record_count: number;
  records: Array<{
    observation_id: string;
    case_id: string;
    timestamp: string;
    merchant_id: string;
    domain: string;
    amount: number;
    decline_reason: string;
    issuer: string;
    treatment: string;
    assigned_propensity: number;
    recovered: number;
    reward_paise: number;
    is_matured: boolean;
    is_eligible: boolean;
    [key: string]: any;
  }>;
}

export interface ApprovalResponse {
  status: string;
  case_id: string;
  dispatch_id: string;
  audit_hash: string;
  approval_snapshot_hash?: string;
  receipt?: any;
}

class ApiClient {
  private baseUrl: string = '/api/v1';
  private connectionStatus: BackendConnectionStatus = 'OFFLINE';
  private statusListeners: Array<(status: BackendConnectionStatus) => void> = [];
  private lastHealthCheck: HealthStatusResponse | null = null;
  private isChecking: boolean = false;
  private forceOffline: boolean = false;
  private pollTimer: any = null;

  private defaultHeaders: Record<string, string> = {
    'Accept': 'application/json',
    'X-API-Key': 'rzp_test_wapsi_key_2026',
  };

  constructor() {
    if (typeof window !== 'undefined') {
      this.forceOffline = localStorage.getItem('wapsi_force_offline') === 'true';
    }
    // Initial health probe
    this.checkHealth().catch(() => {});

    // Periodic health probe every 10s
    if (typeof window !== 'undefined') {
      this.pollTimer = setInterval(() => {
        if (!this.forceOffline) {
          this.checkHealth().catch(() => {});
        }
      }, 10000);
    }
  }

  public onStatusChange(listener: (status: BackendConnectionStatus) => void) {
    this.statusListeners.push(listener);
    listener(this.connectionStatus);
    return () => {
      this.statusListeners = this.statusListeners.filter((l) => l !== listener);
    };
  }

  private setStatus(status: BackendConnectionStatus) {
    if (this.connectionStatus !== status) {
      this.connectionStatus = status;
      this.statusListeners.forEach((l) => l(status));
    }
  }

  public getStatus(): BackendConnectionStatus {
    return this.connectionStatus;
  }

  public getLastHealth(): HealthStatusResponse | null {
    return this.lastHealthCheck;
  }

  public isForcedOffline(): boolean {
    return this.forceOffline;
  }

  public setForceOffline(force: boolean): void {
    this.forceOffline = force;
    if (typeof window !== 'undefined') {
      localStorage.setItem('wapsi_force_offline', String(force));
    }
    if (force) {
      this.setStatus('OFFLINE');
    } else {
      this.setStatus('STARTING');
      this.checkHealth().catch(() => {});
    }
  }

  public toggleMode(): boolean {
    this.setForceOffline(!this.forceOffline);
    return this.forceOffline;
  }

  public setApiKey(key: string): void {
    this.defaultHeaders['X-API-Key'] = key;
  }

  public setMerchantId(merchantId: string): void {
    this.defaultHeaders['X-Merchant-ID'] = merchantId;
  }

  private normalizeUrl(path: string): string {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    if (cleanPath.startsWith('/api/v1/')) {
      return cleanPath;
    }
    if (cleanPath === '/health') {
      return cleanPath;
    }
    return `${this.baseUrl}${cleanPath}`;
  }

  public async checkHealth(): Promise<HealthStatusResponse | null> {
    if (this.forceOffline) {
      this.setStatus('OFFLINE');
      return null;
    }
    if (this.isChecking) return this.lastHealthCheck;
    this.isChecking = true;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 4000);

      const res = await fetch('/health', {
        headers: this.defaultHeaders,
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data: HealthStatusResponse = await res.json();
        this.lastHealthCheck = data;
        if (data.models_ready || data.models_loaded) {
          this.setStatus('LIVE');
        } else {
          this.setStatus('STARTING');
        }
        return data;
      } else {
        this.setStatus('OFFLINE');
        return null;
      }
    } catch {
      this.setStatus('OFFLINE');
      return null;
    } finally {
      this.isChecking = false;
    }
  }

  public async get<T>(path: string, queryParams?: Record<string, string | number | boolean | undefined>): Promise<T> {
    if (this.forceOffline) {
      throw new Error('Causal Engine is in Offline Demo Mode');
    }
    let url = this.normalizeUrl(path);
    if (queryParams) {
      const sp = new URLSearchParams();
      Object.entries(queryParams).forEach(([k, v]) => {
        if (v !== undefined && v !== null) sp.append(k, String(v));
      });
      const qs = sp.toString();
      if (qs) url += `?${qs}`;
    }

    const res = await fetch(url, {
      headers: this.defaultHeaders,
    });

    if (!res.ok) {
      throw new Error(`API Error ${res.status}: ${res.statusText}`);
    }

    return res.json() as Promise<T>;
  }

  public async post<T>(path: string, body?: any): Promise<T> {
    if (this.forceOffline) {
      throw new Error('Causal Engine is in Offline Demo Mode');
    }
    const url = this.normalizeUrl(path);
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        ...this.defaultHeaders,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      let errDetail = res.statusText;
      try {
        const json = await res.json();
        if (json.detail) errDetail = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
      } catch {}
      throw new Error(`API Error ${res.status}: ${errDetail}`);
    }

    return res.json() as Promise<T>;
  }

  public async put<T>(path: string, body?: any): Promise<T> {
    if (this.forceOffline) {
      throw new Error('Causal Engine is in Offline Demo Mode');
    }
    const url = this.normalizeUrl(path);
    const res = await fetch(url, {
      method: 'PUT',
      headers: {
        ...this.defaultHeaders,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      throw new Error(`API Error ${res.status}: ${res.statusText}`);
    }

    return res.json() as Promise<T>;
  }

  // --- Strongly Typed Convenience Methods ---

  public async getWorkerHealth(): Promise<WorkerHealthResponse> {
    return this.get<WorkerHealthResponse>('/workers/health');
  }

  public async getIntegrationsStatus(): Promise<IntegrationsStatusResponse> {
    return this.get<IntegrationsStatusResponse>('/integrations/status');
  }

  public async getObservationalMetrics(merchantId?: string): Promise<ObservationalMetricsResponse> {
    return this.get<ObservationalMetricsResponse>('/observational/metrics', { merchant_id: merchantId });
  }

  public async exportObservationalData(params: {
    merchantId: string;
    eligibleOnly?: boolean;
    startDate?: string;
    endDate?: string;
    limit?: number;
  }): Promise<ObservationalExportResponse> {
    return this.get<ObservationalExportResponse>('/observational/export', {
      merchant_id: params.merchantId,
      eligible_only: params.eligibleOnly !== undefined ? params.eligibleOnly : true,
      start_date: params.startDate,
      end_date: params.endDate,
      limit: params.limit || 500,
    });
  }

  public async getRecoveryMetrics(): Promise<any> {
    return this.get<any>('/recovery/metrics');
  }

  public async getRecoveryCases(params?: {
    domain?: string;
    status?: string;
    search?: string;
    page?: number;
    limit?: number;
  }): Promise<{ cases: any[]; total: number; page: number; limit: number }> {
    return this.get('/recovery/cases', params);
  }

  public async getRecoveryCaseDetail(caseId: string): Promise<any> {
    return this.get(`/recovery/cases/${caseId}`);
  }

  public async approveRecoveryCase(caseId: string, payload?: { action?: string; operatorId?: string }): Promise<ApprovalResponse> {
    return this.post<ApprovalResponse>(`/recovery/cases/${caseId}/approve`, payload || {});
  }

  public async rejectRecoveryCase(caseId: string, payload?: { reason?: string; operatorId?: string }): Promise<any> {
    return this.post<any>(`/recovery/cases/${caseId}/reject`, payload || {});
  }

  public async simulateRecoveryOutcome(caseId: string): Promise<any> {
    return this.post<any>(`/recovery/cases/${caseId}/simulate-recovery`);
  }

  public async getAuditTrail(limit: number = 50): Promise<{ integrity: boolean; total: number; events: any[] }> {
    return this.get('/governance/audit-trail', { limit });
  }

  public async getGovernancePolicies(): Promise<any[]> {
    return this.get('/governance/policies');
  }

  public async getTeeStatus(): Promise<any> {
    return this.get('/governance/tee-status');
  }

  public async getFairnessMetrics(): Promise<any> {
    return this.get('/governance/fairness');
  }

  // --- Synthetic Data Lab & Integration Health Methods ---
  public async getIntegrationsHealth(): Promise<any> {
    return this.get('/integrations/health');
  }

  public async generateSkeleton(seed: number = 42, totalRows: number = 10000): Promise<any> {
    return this.post('/synthetic/jobs/generate-skeleton', { seed, total_rows: totalRows });
  }

  public async enrichNarratives(jobId: string, sampleRows: number = 50, provider?: string): Promise<any> {
    return this.post(`/synthetic/jobs/${jobId}/enrich`, { sample_rows: sampleRows, preferred_provider: provider });
  }

  public async getSyntheticJobStatus(jobId: string): Promise<any> {
    return this.get(`/synthetic/jobs/${jobId}/status`);
  }

  public async getSyntheticPreview(jobId: string, limit: number = 20, offset: number = 0): Promise<any> {
    return this.get(`/synthetic/jobs/${jobId}/preview`, { limit, offset });
  }

  public async cancelSyntheticJob(jobId: string): Promise<any> {
    return this.post(`/synthetic/jobs/${jobId}/cancel`);
  }

  public async getSyntheticDatasets(): Promise<any> {
    return this.get('/synthetic/datasets');
  }
}

export const apiClient = new ApiClient();
