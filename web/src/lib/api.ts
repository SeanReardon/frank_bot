/**
 * Frank Bot API client module.
 *
 * Provides typed API functions for the Frank Bot backend.
 */

// Global state
let apiBase = '/api';
let sessionToken: string | null = null;

/**
 * Configure the API client.
 */
export function configure(options: { apiBase?: string; sessionToken?: string }) {
  if (options.apiBase !== undefined) {
    apiBase = options.apiBase;
  }
  if (options.sessionToken !== undefined) {
    sessionToken = options.sessionToken || null;
  }
}

/**
 * Get current configuration.
 */
export function getConfig(): { apiBase: string; sessionToken: string | null } {
  return { apiBase, sessionToken };
}

/**
 * Error thrown when authentication fails.
 */
export class AuthError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = 'AuthError';
  }
}

/**
 * Make an API request.
 */
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  // Add session token if available
  if (sessionToken) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${sessionToken}`;
  }

  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers,
    credentials: 'include', // Include cookies for SSO
  });

  if (response.status === 401 || response.status === 403) {
    throw new AuthError('Not authenticated', response.status);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API error ${response.status}: ${errorText}`);
  }

  return response.json();
}

// Types

export interface TelegramStatus {
  status: 'not_configured' | 'needs_auth' | 'connected';
  account?: {
    name: string | null;
    username: string | null;
    phone: string | null;
  };
}

export interface TelegramAuthStartResponse {
  status: 'code_sent' | 'already_authorized' | 'error';
  phoneCodeHash?: string;
  error?: string;
}

export interface TelegramAuthVerifyResponse {
  status: 'success' | 'invalid_code' | 'needs_2fa' | 'error';
  error?: string;
}

export interface TelegramAuth2FAResponse {
  status: 'success' | 'invalid_password' | 'error';
  error?: string;
}

export interface TelegramTestResponse {
  connected: boolean;
  dialogs?: Array<{
    id: number;
    name: string;
    type: string;
  }>;
  error?: string;
}

export interface Script {
  name: string;
  description: string;
  execution_count: number;
  last_run_at: string | null;
}

export interface ScriptsResponse {
  scripts: Script[];
}

export interface Job {
  id: string;
  script_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  stdout: string | null;
  stderr: string | null;
  result: unknown;
  error: string | null;
}

export interface JobsResponse {
  jobs: Job[];
}

// API Functions

/**
 * Get Telegram connection status.
 */
export async function getTelegramStatus(): Promise<TelegramStatus> {
  return request<TelegramStatus>('/telegram/status');
}

/**
 * Start Telegram authentication flow.
 */
export async function startTelegramAuth(phone?: string): Promise<TelegramAuthStartResponse> {
  return request<TelegramAuthStartResponse>('/telegram/auth/start', {
    method: 'POST',
    body: JSON.stringify({ phone }),
  });
}

/**
 * Verify Telegram authentication code.
 */
export async function verifyTelegramCode(
  code: string,
  phoneCodeHash: string
): Promise<TelegramAuthVerifyResponse> {
  return request<TelegramAuthVerifyResponse>('/telegram/auth/verify', {
    method: 'POST',
    body: JSON.stringify({ code, phoneCodeHash }),
  });
}

/**
 * Submit Telegram 2FA password.
 */
export async function submitTelegram2FA(password: string): Promise<TelegramAuth2FAResponse> {
  return request<TelegramAuth2FAResponse>('/telegram/auth/2fa', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

/**
 * Test Telegram connection.
 */
export async function testTelegramConnection(): Promise<TelegramTestResponse> {
  return request<TelegramTestResponse>('/telegram/test');
}

/**
 * Get list of meta scripts.
 */
export async function getScripts(): Promise<ScriptsResponse> {
  return request<ScriptsResponse>('/frank/scripts');
}

/**
 * Get list of job executions.
 */
export async function getJobs(): Promise<JobsResponse> {
  return request<JobsResponse>('/frank/jobs');
}
