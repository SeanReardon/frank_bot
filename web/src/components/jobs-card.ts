/**
 * Jobs card component for Frank Bot dashboard.
 *
 * Displays list of job executions with status and details.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { JobSummary, Job } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

type StatusFilter = 'all' | 'pending' | 'running' | 'completed' | 'failed' | 'timeout';

/**
 * Jobs card component.
 *
 * @element jobs-card
 */
@customElement('jobs-card')
export class JobsCard extends LitElement {
  static styles = css`
    ${unsafeCSS(tokensCSS)}

    :host {
      display: block;
    }

    .card {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-md);
      padding: var(--spacing-lg);
      /* Kente blue left accent - jobs represent activity/work */
      border-left: 3px solid var(--kente-blue);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: var(--spacing-md);
      flex-wrap: wrap;
      gap: var(--spacing-sm);
    }

    .card-title {
      font-size: var(--font-size-lg);
      font-weight: 600;
      margin: 0;
      color: var(--kente-gold-light);
    }

    .header-controls {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
    }

    .button {
      padding: var(--spacing-sm) var(--spacing-md);
      border-radius: var(--border-radius-sm);
      border: none;
      cursor: pointer;
      font-size: var(--font-size-base);
      font-weight: 600;
      transition: all var(--transition-fast);
    }

    .button-secondary {
      background: var(--color-surface-hover);
      color: var(--color-text);
      border: 1px solid var(--color-border);
    }

    .button-secondary:hover:not(:disabled) {
      border-color: var(--kente-gold);
      color: var(--kente-gold-light);
    }

    .button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .button-icon {
      padding: var(--spacing-xs) var(--spacing-sm);
    }

    .filter-select {
      padding: var(--spacing-xs) var(--spacing-sm);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      background: var(--color-surface-hover);
      color: var(--color-text);
      font-size: var(--font-size-sm);
      cursor: pointer;
    }

    .filter-select:focus {
      outline: none;
      border-color: var(--kente-gold);
    }

    .auto-refresh {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }

    .auto-refresh input {
      cursor: pointer;
      accent-color: var(--kente-gold);
    }

    .loading {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      color: var(--color-text-muted);
    }

    .spinner {
      width: 16px;
      height: 16px;
      border: 2px solid var(--color-border);
      border-top-color: var(--kente-gold);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .message {
      padding: var(--spacing-md);
      border-radius: var(--border-radius-sm);
      margin-top: var(--spacing-md);
    }

    .message.error {
      background: color-mix(in srgb, var(--kente-red) 15%, transparent);
      border: 1px solid var(--kente-red);
    }

    .empty-state {
      text-align: center;
      color: var(--color-text-muted);
      padding: var(--spacing-xl);
    }

    .jobs-list {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .job-item {
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      overflow: hidden;
      border-left: 2px solid transparent;
      transition: border-color var(--transition-fast);
    }

    .job-item:hover {
      border-left-color: var(--kente-blue);
    }

    .job-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--spacing-md);
      cursor: pointer;
      transition: background var(--transition-fast);
      gap: var(--spacing-md);
    }

    .job-header:hover {
      background: var(--color-border);
    }

    .job-info {
      flex: 1;
      min-width: 0;
      display: flex;
      align-items: center;
      gap: var(--spacing-md);
    }

    .job-script {
      font-weight: 600;
      word-break: break-word;
    }

    .status-badge {
      display: inline-block;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
      font-weight: 500;
      white-space: nowrap;
    }

    .status-badge.pending {
      background: var(--color-border);
      color: var(--color-text);
    }

    .status-badge.running {
      background: var(--kente-blue);
      color: white;
    }

    .status-badge.completed {
      background: var(--kente-green);
      color: white;
    }

    .status-badge.failed {
      background: var(--kente-red);
      color: white;
    }

    .status-badge.timeout {
      background: var(--kente-orange);
      color: white;
    }

    .job-meta {
      display: flex;
      gap: var(--spacing-md);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      white-space: nowrap;
    }

    .expand-icon {
      transition: transform var(--transition-fast);
      color: var(--kente-gold);
    }

    .expand-icon.expanded {
      transform: rotate(180deg);
    }

    .job-details {
      padding: 0 var(--spacing-md) var(--spacing-md);
      border-top: 1px solid var(--color-border);
    }

    .job-details h4 {
      font-size: var(--font-size-sm);
      color: var(--kente-gold);
      margin: var(--spacing-md) 0 var(--spacing-sm);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .output-block {
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      overflow-x: auto;
      font-family: monospace;
      font-size: var(--font-size-sm);
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 300px;
      overflow-y: auto;
    }

    .output-block.error {
      border-color: var(--kente-red);
      color: var(--kente-red);
    }

    .result-block {
      background: var(--color-bg);
      border: 1px solid var(--kente-green);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      overflow-x: auto;
      font-family: monospace;
      font-size: var(--font-size-sm);
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 300px;
      overflow-y: auto;
    }

    .job-id {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      margin-top: var(--spacing-md);
    }
  `;

  @state() private _jobs: JobSummary[] = [];
  @state() private _loading = true;
  @state() private _error: string | null = null;
  @state() private _expandedJobId: string | null = null;
  @state() private _jobDetails: Map<string, Job> = new Map();
  @state() private _loadingDetails: Set<string> = new Set();
  @state() private _statusFilter: StatusFilter = 'all';
  @state() private _autoRefresh = false;
  private _refreshInterval: number | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._fetchJobs();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._stopAutoRefresh();
  }

  private async _fetchJobs() {
    this._loading = true;
    this._error = null;

    try {
      const statusParam = this._statusFilter === 'all' ? undefined : this._statusFilter;
      const response = await api.getJobs(statusParam);
      this._jobs = response.jobs;
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch jobs';
    } finally {
      this._loading = false;
    }
  }

  private async _toggleExpand(jobId: string) {
    if (this._expandedJobId === jobId) {
      this._expandedJobId = null;
      return;
    }

    this._expandedJobId = jobId;

    // Load job details if not already loaded
    if (!this._jobDetails.has(jobId) && !this._loadingDetails.has(jobId)) {
      await this._loadJobDetails(jobId);
    }
  }

  private async _loadJobDetails(jobId: string) {
    this._loadingDetails = new Set([...this._loadingDetails, jobId]);

    try {
      const job = await api.getJob(jobId);
      this._jobDetails = new Map([...this._jobDetails, [jobId, job]]);
    } catch (err) {
      console.error('Failed to load job details:', err);
    } finally {
      const newSet = new Set(this._loadingDetails);
      newSet.delete(jobId);
      this._loadingDetails = newSet;
    }
  }

  private _handleFilterChange(e: Event) {
    const select = e.target as HTMLSelectElement;
    this._statusFilter = select.value as StatusFilter;
    this._fetchJobs();
  }

  private _handleAutoRefreshChange(e: Event) {
    const checkbox = e.target as HTMLInputElement;
    this._autoRefresh = checkbox.checked;

    if (this._autoRefresh) {
      this._startAutoRefresh();
    } else {
      this._stopAutoRefresh();
    }
  }

  private _startAutoRefresh() {
    this._stopAutoRefresh();
    this._refreshInterval = window.setInterval(() => {
      this._fetchJobs();
      // Also refresh expanded job details if it's running
      if (this._expandedJobId) {
        const job = this._jobs.find(j => j.job_id === this._expandedJobId);
        if (job && (job.status === 'running' || job.status === 'pending')) {
          this._loadJobDetails(this._expandedJobId);
        }
      }
    }, 5000); // Refresh every 5 seconds
  }

  private _stopAutoRefresh() {
    if (this._refreshInterval !== null) {
      window.clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
  }

  private _formatDate(isoDate: string | null): string {
    if (!isoDate) return '—';
    try {
      const date = new Date(isoDate);
      return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoDate;
    }
  }

  private _calculateDuration(startedAt: string | null, completedAt: string | null): string {
    if (!startedAt) return '—';

    const start = new Date(startedAt);
    const end = completedAt ? new Date(completedAt) : new Date();
    const durationMs = end.getTime() - start.getTime();

    if (durationMs < 1000) {
      return `${durationMs}ms`;
    } else if (durationMs < 60000) {
      return `${(durationMs / 1000).toFixed(1)}s`;
    } else {
      const minutes = Math.floor(durationMs / 60000);
      const seconds = ((durationMs % 60000) / 1000).toFixed(0);
      return `${minutes}m ${seconds}s`;
    }
  }

  private _getScriptNameFromId(scriptId: string): string {
    // Script IDs are like "2024-01-15T10-30-00Z-my-script"
    // Extract the slug part after the timestamp
    const parts = scriptId.split('-');
    if (parts.length > 4) {
      // Skip timestamp parts (YYYY-MM-DDTHH-MM-SSZ = first 4 parts)
      return parts.slice(4).join('-');
    }
    return scriptId;
  }

  private _renderContent() {
    if (this._loading && this._jobs.length === 0) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading jobs...</span>
        </div>
      `;
    }

    if (this._error) {
      return html`
        <div class="message error">${this._error}</div>
      `;
    }

    if (this._jobs.length === 0) {
      return html`
        <div class="empty-state">
          <p>No jobs found${this._statusFilter !== 'all' ? ` with status "${this._statusFilter}"` : ''}.</p>
          <p>Jobs are created when scripts are executed via the /frank/execute endpoint.</p>
        </div>
      `;
    }

    return html`
      <div class="jobs-list">
        ${this._jobs.map(job => this._renderJob(job))}
      </div>
    `;
  }

  private _renderJob(job: JobSummary) {
    const isExpanded = this._expandedJobId === job.job_id;
    const details = this._jobDetails.get(job.job_id);
    const isLoadingDetails = this._loadingDetails.has(job.job_id);
    const scriptName = this._getScriptNameFromId(job.script_id);
    const duration = this._calculateDuration(job.started_at, job.completed_at);

    return html`
      <div class="job-item">
        <div
          class="job-header"
          @click=${() => this._toggleExpand(job.job_id)}
          role="button"
          tabindex="0"
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              this._toggleExpand(job.job_id);
            }
          }}
        >
          <div class="job-info">
            <span class="job-script">${scriptName}</span>
            <span class="status-badge ${job.status}">${job.status}</span>
          </div>
          <div class="job-meta">
            <span title="Started">${this._formatDate(job.started_at)}</span>
            <span title="Duration">${duration}</span>
            <span class="expand-icon ${isExpanded ? 'expanded' : ''}">▼</span>
          </div>
        </div>

        ${isExpanded ? html`
          <div class="job-details">
            ${isLoadingDetails ? html`
              <div class="loading">
                <div class="spinner"></div>
                <span>Loading details...</span>
              </div>
            ` : details ? this._renderJobDetails(details) : html`
              <p>Failed to load job details.</p>
            `}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _renderJobDetails(job: Job) {
    return html`
      ${job.stdout ? html`
        <h4>Output (stdout)</h4>
        <div class="output-block">${job.stdout}</div>
      ` : nothing}

      ${job.stderr ? html`
        <h4>Errors (stderr)</h4>
        <div class="output-block error">${job.stderr}</div>
      ` : nothing}

      ${job.result !== null && job.result !== undefined ? html`
        <h4>Result</h4>
        <div class="result-block">${typeof job.result === 'string' ? job.result : JSON.stringify(job.result, null, 2)}</div>
      ` : nothing}

      ${job.error ? html`
        <h4>Error</h4>
        <div class="output-block error">${job.error}</div>
      ` : nothing}

      ${Object.keys(job.params).length > 0 ? html`
        <h4>Parameters</h4>
        <div class="output-block">${JSON.stringify(job.params, null, 2)}</div>
      ` : nothing}

      <div class="job-id">
        <strong>Job ID:</strong> ${job.job_id}<br>
        <strong>Script ID:</strong> ${job.script_id}
      </div>
    `;
  }

  render() {
    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Jobs</h3>
          <div class="header-controls">
            <select
              class="filter-select"
              @change=${this._handleFilterChange}
              .value=${this._statusFilter}
            >
              <option value="all">All</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="timeout">Timeout</option>
            </select>
            <label class="auto-refresh">
              <input
                type="checkbox"
                ?checked=${this._autoRefresh}
                @change=${this._handleAutoRefreshChange}
              />
              Auto-refresh
            </label>
            <button
              class="button button-secondary button-icon"
              @click=${this._fetchJobs}
              ?disabled=${this._loading}
              title="Refresh"
            >
              ↻
            </button>
          </div>
        </div>
        ${this._renderContent()}
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'jobs-card': JobsCard;
  }
}
