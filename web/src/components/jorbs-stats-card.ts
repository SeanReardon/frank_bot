/**
 * Jorbs stats overview card component.
 *
 * Displays aggregate metrics and status counts for jorbs.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { JorbsStatsResponse } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

/**
 * Jorbs stats card component.
 *
 * @element jorbs-stats-card
 * @fires brief-me - Fired when the Brief Me button is clicked
 */
@customElement('jorbs-stats-card')
export class JorbsStatsCard extends LitElement {
  static styles = css`
    ${unsafeCSS(tokensCSS)}

    :host {
      display: block;
    }

    .card {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-md);
      padding: var(--spacing-md);
      /* Kente gold accent */
      border-left: 3px solid var(--kente-gold);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: var(--spacing-md);
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
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      border: none;
      cursor: pointer;
      font-size: var(--font-size-sm);
      font-weight: 600;
      transition: all var(--transition-fast);
    }

    .button-primary {
      background: var(--kente-gold);
      color: var(--color-bg);
    }

    .button-primary:hover:not(:disabled) {
      background: var(--kente-gold-light);
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

    .loading {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      color: var(--color-text-muted);
      padding: var(--spacing-md);
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

    .error {
      background: color-mix(in srgb, var(--kente-red) 15%, transparent);
      border: 1px solid var(--kente-red);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      color: var(--kente-red);
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: var(--spacing-md);
    }

    .stat-item {
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      text-align: center;
    }

    .stat-value {
      font-size: var(--font-size-xl);
      font-weight: 700;
      color: var(--color-text);
      margin-bottom: var(--spacing-xs);
    }

    .stat-label {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }

    .stat-value.gold {
      color: var(--kente-gold-light);
    }

    .stat-value.green {
      color: var(--kente-green);
    }

    .stat-value.orange {
      color: var(--kente-orange);
    }

    .stat-value.blue {
      color: var(--kente-blue);
    }

    .status-row {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-sm);
      margin-bottom: var(--spacing-md);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: var(--spacing-xs);
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
      font-weight: 500;
    }

    .status-badge.running {
      background: color-mix(in srgb, var(--kente-blue) 20%, transparent);
      color: var(--kente-blue);
      border: 1px solid var(--kente-blue);
    }

    .status-badge.paused {
      background: color-mix(in srgb, var(--kente-orange) 20%, transparent);
      color: var(--kente-orange);
      border: 1px solid var(--kente-orange);
    }

    .status-badge.complete {
      background: color-mix(in srgb, var(--kente-green) 20%, transparent);
      color: var(--kente-green);
      border: 1px solid var(--kente-green);
    }

    .status-badge.failed {
      background: color-mix(in srgb, var(--kente-red) 20%, transparent);
      color: var(--kente-red);
      border: 1px solid var(--kente-red);
    }

    .status-badge.planning,
    .status-badge.cancelled {
      background: var(--color-surface-hover);
      color: var(--color-text-muted);
      border: 1px solid var(--color-border);
    }

    .status-count {
      font-weight: 700;
    }

    .metrics-row {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-md);
      padding-top: var(--spacing-md);
      border-top: 1px solid var(--color-border);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }

    .metric-item {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
    }

    .metric-value {
      font-weight: 600;
      color: var(--color-text);
    }
  `;

  @state() private _stats: JorbsStatsResponse | null = null;
  @state() private _loading = true;
  @state() private _error: string | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._fetchStats();
  }

  private async _fetchStats() {
    this._loading = true;
    this._error = null;

    try {
      this._stats = await api.getJorbsStats('all');
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch stats';
    } finally {
      this._loading = false;
    }
  }

  private _handleBriefMe() {
    this.dispatchEvent(
      new CustomEvent('brief-me', {
        bubbles: true,
        composed: true,
      })
    );
  }

  private _formatCost(cost: number): string {
    if (cost === 0) return '$0.00';
    if (cost < 0.01) return '<$0.01';
    return `$${cost.toFixed(2)}`;
  }

  private _formatNumber(num: number): string {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  }

  render() {
    if (this._loading) {
      return html`
        <div class="card">
          <div class="loading">
            <div class="spinner"></div>
            <span>Loading stats...</span>
          </div>
        </div>
      `;
    }

    if (this._error) {
      return html`
        <div class="card">
          <div class="error">${this._error}</div>
        </div>
      `;
    }

    if (!this._stats) {
      return nothing;
    }

    const stats = this._stats;
    const { by_status, metrics } = stats;

    // Calculate active (open) count
    const openCount = by_status.planning + by_status.running + by_status.paused;

    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Jorbs Overview</h3>
          <div class="header-controls">
            <button
              class="button button-primary"
              @click=${this._handleBriefMe}
            >
              Brief Me
            </button>
            <button
              class="button button-secondary"
              @click=${this._fetchStats}
              ?disabled=${this._loading}
              title="Refresh"
            >
              ↻
            </button>
          </div>
        </div>

        <div class="status-row">
          ${by_status.running > 0 ? html`
            <span class="status-badge running">
              <span class="status-count">${by_status.running}</span> Running
            </span>
          ` : nothing}
          ${by_status.paused > 0 ? html`
            <span class="status-badge paused">
              <span class="status-count">${by_status.paused}</span> Paused
            </span>
          ` : nothing}
          ${by_status.planning > 0 ? html`
            <span class="status-badge planning">
              <span class="status-count">${by_status.planning}</span> Planning
            </span>
          ` : nothing}
          ${by_status.complete > 0 ? html`
            <span class="status-badge complete">
              <span class="status-count">${by_status.complete}</span> Complete
            </span>
          ` : nothing}
          ${by_status.failed > 0 ? html`
            <span class="status-badge failed">
              <span class="status-count">${by_status.failed}</span> Failed
            </span>
          ` : nothing}
          ${by_status.cancelled > 0 ? html`
            <span class="status-badge cancelled">
              <span class="status-count">${by_status.cancelled}</span> Cancelled
            </span>
          ` : nothing}
        </div>

        <div class="stats-grid">
          <div class="stat-item">
            <div class="stat-value gold">${openCount}</div>
            <div class="stat-label">Open Jorbs</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">${this._formatNumber(metrics.total_messages)}</div>
            <div class="stat-label">Messages</div>
          </div>
          <div class="stat-item">
            <div class="stat-value green">${stats.success_rate}%</div>
            <div class="stat-label">Success Rate</div>
          </div>
          <div class="stat-item">
            <div class="stat-value blue">${this._formatCost(metrics.total_cost)}</div>
            <div class="stat-label">Total Cost</div>
          </div>
        </div>

        <div class="metrics-row">
          <div class="metric-item">
            <span class="metric-value">${this._formatNumber(metrics.total_tokens)}</span>
            <span>tokens used</span>
          </div>
          <div class="metric-item">
            <span class="metric-value">${metrics.total_context_resets}</span>
            <span>context resets</span>
          </div>
          <div class="metric-item">
            <span class="metric-value">${stats.total_jorbs}</span>
            <span>total jorbs</span>
          </div>
        </div>
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'jorbs-stats-card': JorbsStatsCard;
  }
}
