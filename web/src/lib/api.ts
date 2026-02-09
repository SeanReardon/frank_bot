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

export interface TelegramMessage {
  id: number;
  text: string | null;
  date: string;
  sender: string;
  is_outgoing: boolean;
}

export interface TelegramTestResponse {
  connected: boolean;
  chat_name?: string;
  message_count?: number;
  messages?: TelegramMessage[];
  error?: string;
}

export interface ScriptParameter {
  name: string;
  type: string | null;
  description: string;
}

export interface Script {
  id: string;
  slug: string;
  description: string;
  parameters: ScriptParameter[];
  example: string | null;
  created_at: string;
}

export interface ScriptsResponse {
  count: number;
  scripts: Script[];
}

export interface JobSummary {
  job_id: string;
  script_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout';
  started_at: string | null;
  completed_at: string | null;
}

export interface Job {
  job_id: string;
  script_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout';
  params: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  stdout: string;
  stderr: string;
  result: unknown;
  error: string | null;
}

export interface JobsResponse {
  count: number;
  jobs: JobSummary[];
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
  return request<ScriptsResponse>('/frank/script/list');
}

/**
 * Get a script's source code by ID.
 */
export async function getScriptCode(scriptId: string): Promise<string> {
  const response = await fetch(`${apiBase}/frank/script/get?id=${encodeURIComponent(scriptId)}`, {
    credentials: 'include',
  });

  if (response.status === 401 || response.status === 403) {
    throw new AuthError('Not authenticated', response.status);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API error ${response.status}: ${errorText}`);
  }

  return response.text();
}

/**
 * Get list of job executions.
 */
export async function getJobs(status?: string): Promise<JobsResponse> {
  const params = status ? `?status=${encodeURIComponent(status)}` : '';
  return request<JobsResponse>(`/frank/script/task/list${params}`);
}

/**
 * Get a specific job by ID.
 */
export async function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/frank/script/task/status?job_id=${encodeURIComponent(jobId)}`);
}

// Telegram Bot types and functions

export interface TelegramBotStatus {
  configured: boolean;
  chatId?: string;
}

export interface TelegramBotTestResponse {
  success: boolean;
  error?: string;
}

/**
 * Get Telegram Bot notification service status.
 */
export async function getTelegramBotStatus(): Promise<TelegramBotStatus> {
  return request<TelegramBotStatus>('/telegram-bot/status');
}

/**
 * Test Telegram Bot notification by sending a test message.
 */
export async function testTelegramBot(): Promise<TelegramBotTestResponse> {
  return request<TelegramBotTestResponse>('/telegram-bot/test', {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

// SMS types and functions

export interface SmsMessage {
  timestamp: string;
  direction: 'inbound' | 'outbound';
  contact: string | null;
  phone: string;
  preview: string;
  hasAttachments: boolean;
  jorbId: string | null;
}

export interface SmsMessagesResponse {
  count: number;
  messages: SmsMessage[];
}

export interface GetSmsMessagesOptions {
  limit?: number;
  contact?: string;
  phone?: string;
  direction?: 'inbound' | 'outbound';
}

/**
 * Get SMS messages with optional filtering.
 */
export async function getSmsMessages(options: GetSmsMessagesOptions = {}): Promise<SmsMessagesResponse> {
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set('limit', String(options.limit));
  if (options.contact) params.set('contact', options.contact);
  if (options.phone) params.set('phone', options.phone);
  if (options.direction) params.set('direction', options.direction);

  const queryString = params.toString();
  const path = `/sms/messages${queryString ? `?${queryString}` : ''}`;
  return request<SmsMessagesResponse>(path);
}

// Version types and functions

export interface VersionInfo {
  api: {
    commit: string;
    commit_url: string | null;
  };
}

/**
 * Get API version info.
 */
export async function getVersion(): Promise<VersionInfo> {
  return request<VersionInfo>('/version');
}

/**
 * Get the web build commit from Vite env.
 */
export function getWebCommit(): string {
  return (import.meta as any).env?.VITE_GIT_COMMIT || 'dev';
}

// Jorb types and functions

export type JorbStatus = 'planning' | 'running' | 'paused' | 'complete' | 'failed' | 'cancelled';
export type JorbChannel = 'telegram' | 'sms' | 'email';

export interface JorbContact {
  identifier: string;
  channel: JorbChannel;
  name?: string;
}

export interface JorbMetrics {
  messages_in: number;
  messages_out: number;
  tokens_used: number;
  estimated_cost: number;
  context_resets: number;
}

export interface JorbOutcome {
  result: string | null;
  completed_at: string | null;
  failure_reason: string | null;
}

export interface JorbCheckpoint {
  id: string;
  timestamp: string;
  summary: string;
  token_count: number | null;
}

export interface Jorb {
  jorb_id: string;
  name: string;
  status: JorbStatus;
  original_plan: string;
  contacts: JorbContact[];
  progress_summary: string | null;
  created_at: string;
  updated_at: string;
  paused_reason: string | null;
  needs_approval_for: string | null;
  awaiting: string | null;
  metrics: JorbMetrics;
  outcome?: JorbOutcome;
}

export interface JorbMessage {
  id: string;
  jorb_id: string;
  timestamp: string;
  direction: 'inbound' | 'outbound';
  channel: JorbChannel;
  sender: string | null;
  sender_name: string | null;
  recipient: string | null;
  content: string;
  agent_reasoning: string | null;
}

export interface JorbStatusCounts {
  planning: number;
  running: number;
  paused: number;
  complete: number;
  failed: number;
  cancelled: number;
}

export interface JorbAggregateMetrics {
  total_jorbs: number;
  total_messages_in: number;
  total_messages_out: number;
  total_messages: number;
  total_tokens: number;
  total_cost: number;
  total_context_resets: number;
  by_status: JorbStatusCounts;
}

export interface JorbsResponse {
  count: number;
  jorbs: Jorb[];
  aggregate_metrics: JorbAggregateMetrics;
}

export interface JorbDetailResponse extends Jorb {
  messages?: JorbMessage[];
  checkpoints?: JorbCheckpoint[];
}

export interface JorbMessagesResponse {
  count: number;
  messages: JorbMessage[];
}

export interface ApproveJorbResponse {
  success: boolean;
  jorb_id: string;
  status: JorbStatus;
  message?: string;
}

export interface CancelJorbResponse {
  success: boolean;
  jorb_id: string;
  status: JorbStatus;
  message?: string;
}

export interface GetJorbsOptions {
  status?: 'open' | 'closed' | 'all';
}

export interface GetJorbMessagesOptions {
  limit?: number;
  offset?: number;
}

/**
 * Get list of jorbs.
 */
export async function getJorbs(options: GetJorbsOptions = {}): Promise<JorbsResponse> {
  const params = new URLSearchParams();
  if (options.status) params.set('status', options.status);

  const queryString = params.toString();
  const path = `/actions/jorbs/list${queryString ? `?${queryString}` : ''}`;
  return request<JorbsResponse>(path);
}

/**
 * Get a specific jorb by ID.
 */
export async function getJorb(jorbId: string, includeMessages = false, messageLimit = 50): Promise<JorbDetailResponse> {
  const params = new URLSearchParams();
  if (includeMessages) params.set('include_messages', 'true');
  if (messageLimit !== 50) params.set('message_limit', String(messageLimit));

  const queryString = params.toString();
  const path = `/actions/jorbs/${encodeURIComponent(jorbId)}/get${queryString ? `?${queryString}` : ''}`;
  return request<JorbDetailResponse>(path);
}

/**
 * Get messages for a jorb.
 */
export async function getJorbMessages(jorbId: string, options: GetJorbMessagesOptions = {}): Promise<JorbMessagesResponse> {
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set('limit', String(options.limit));
  if (options.offset !== undefined) params.set('offset', String(options.offset));

  const queryString = params.toString();
  const path = `/actions/jorbs/${encodeURIComponent(jorbId)}/messages/get${queryString ? `?${queryString}` : ''}`;
  return request<JorbMessagesResponse>(path);
}

/**
 * Approve a paused jorb.
 */
export async function approveJorb(jorbId: string, decision: string): Promise<ApproveJorbResponse> {
  const params = new URLSearchParams();
  params.set('decision', decision);

  return request<ApproveJorbResponse>(`/actions/jorbs/${encodeURIComponent(jorbId)}/approve?${params.toString()}`);
}

/**
 * Cancel a jorb.
 */
export async function cancelJorb(jorbId: string, reason?: string): Promise<CancelJorbResponse> {
  const params = new URLSearchParams();
  if (reason) params.set('reason', reason);

  const queryString = params.toString();
  const path = `/actions/jorbs/${encodeURIComponent(jorbId)}/cancel${queryString ? `?${queryString}` : ''}`;
  return request<CancelJorbResponse>(path);
}

// Jorb Stats types and functions

export interface JorbsStatsResponse {
  status_filter: string;
  total_jorbs: number;
  by_status: JorbStatusCounts;
  metrics: {
    total_messages: number;
    total_messages_in: number;
    total_messages_out: number;
    total_tokens: number;
    total_cost: number;
    total_context_resets: number;
  };
  success_rate: number;
}

/**
 * Get aggregate jorbs statistics.
 */
export async function getJorbsStats(status?: 'open' | 'closed' | 'all'): Promise<JorbsStatsResponse> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);

  const queryString = params.toString();
  const path = `/actions/jorbs/stats${queryString ? `?${queryString}` : ''}`;
  return request<JorbsStatsResponse>(path);
}

// Jorb Brief types and functions

export interface JorbActivityMessage {
  timestamp: string;
  direction: 'inbound' | 'outbound';
  content: string;
}

export interface JorbActivitySummary {
  jorb_id: string;
  name: string;
  status: JorbStatus;
  message_count: number;
  recent_messages: JorbActivityMessage[];
  awaiting: string | null;
}

export interface PendingDecision {
  jorb_id: string;
  name: string;
  paused_reason: string | null;
  needs_approval_for: string | null;
  options: string[];
}

export interface JorbBriefResponse {
  briefing_time: string;
  since: string;
  last_briefing: string | null;
  needs_attention: number;
  activity_summary: JorbActivitySummary[];
  highlights: string[];
  pending_decisions: PendingDecision[];
  total_open_jorbs: number;
  recently_completed: number;
  aggregate_metrics: {
    total_jorbs: number;
    total_messages: number;
    total_cost: number;
    by_status: JorbStatusCounts;
  };
}

export interface GetJorbsBriefOptions {
  hours?: number;
  update_timestamp?: boolean;
}

/**
 * Get jorbs activity briefing.
 */
export async function getJorbsBrief(options: GetJorbsBriefOptions = {}): Promise<JorbBriefResponse> {
  const params = new URLSearchParams();
  if (options.hours !== undefined) params.set('hours', String(options.hours));
  if (options.update_timestamp !== undefined) params.set('update_timestamp', String(options.update_timestamp));

  const queryString = params.toString();
  const path = `/actions/jorbs/brief${queryString ? `?${queryString}` : ''}`;
  return request<JorbBriefResponse>(path);
}

// System Status types and functions

export interface SystemComponentStatus {
  configured: boolean;
  model?: string;
  description: string;
  initialized?: boolean;
  telegram_configured?: boolean;
  agent_configured?: boolean;
  pending_messages?: number;
  debounce_telegram_seconds?: number;
  debounce_sms_seconds?: number;
}

export interface SystemJorbsStatus {
  total_open: number;
  by_status: {
    planning: number;
    running: number;
    paused: number;
  };
  needs_attention: number;
}

export interface AndroidPhoneStatus {
  connected: boolean;
  device_model?: string | null;
  android_version?: string | null;
  battery_level?: number | null;
  wifi_ssid?: string | null;
  error?: string | null;
  description: string;
}

export interface SystemStatusResponse {
  message: string;
  healthy: boolean;
  switchboard: SystemComponentStatus;
  agent_runner: SystemComponentStatus;
  telegram_router: SystemComponentStatus;
  message_buffer: SystemComponentStatus;
  jorbs: SystemJorbsStatus;
  android_phone?: AndroidPhoneStatus;
}

/**
 * Get system orchestration status.
 */
export async function getSystemStatus(): Promise<SystemStatusResponse> {
  return request<SystemStatusResponse>('/system/status');
}
