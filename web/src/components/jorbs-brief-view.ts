/**
 * Jorbs brief view component.
 *
 * Displays activity summary since last briefing with pending decisions.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { JorbBriefResponse, PendingDecision, JorbActivitySummary } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

/**
 * Jorbs brief view component.
 *
 * @element jorbs-brief-view
 * @fires close - Fired when user wants to close the brief view
 * @fires jorb-select - Fired when a jorb is selected for detailed view
 */
@customElement('jorbs-brief-view')
export class JorbsBriefView extends LitElement {
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
      border-left: 3px solid var(--kente-gold);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: var(--spacing-lg);
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

    .button-danger {
      background: var(--kente-red);
      color: white;
    }

    .button-danger:hover:not(:disabled) {
      opacity: 0.9;
    }

    .button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: var(--spacing-sm);
      color: var(--color-text-muted);
      padding: var(--spacing-xl);
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

    .brief-meta {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-md);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      margin-bottom: var(--spacing-lg);
      padding-bottom: var(--spacing-md);
      border-bottom: 1px solid var(--color-border);
    }

    .section {
      margin-bottom: var(--spacing-lg);
    }

    .section:last-child {
      margin-bottom: 0;
    }

    .section-title {
      font-size: var(--font-size-base);
      font-weight: 600;
      color: var(--kente-gold);
      margin: 0 0 var(--spacing-md);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .highlights {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-sm);
    }

    .highlight-item {
      display: inline-flex;
      align-items: center;
      gap: var(--spacing-xs);
      padding: var(--spacing-xs) var(--spacing-sm);
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
    }

    .pending-decisions {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-md);
    }

    .decision-item {
      background: color-mix(in srgb, var(--kente-orange) 15%, transparent);
      border: 1px solid var(--kente-orange);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
    }

    .decision-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: var(--spacing-sm);
    }

    .decision-name {
      font-weight: 600;
      color: var(--color-text);
    }

    .decision-reason {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      margin-bottom: var(--spacing-md);
    }

    .decision-actions {
      display: flex;
      gap: var(--spacing-sm);
      flex-wrap: wrap;
    }

    .approval-input {
      flex: 1;
      min-width: 200px;
      padding: var(--spacing-sm);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      background: var(--color-surface);
      color: var(--color-text);
      font-size: var(--font-size-base);
    }

    .approval-input:focus {
      outline: none;
      border-color: var(--kente-gold);
    }

    .activity-list {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .activity-item {
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      cursor: pointer;
      transition: border-color var(--transition-fast);
      border-left: 2px solid transparent;
    }

    .activity-item:hover {
      border-left-color: var(--kente-gold);
    }

    .activity-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: var(--spacing-xs);
    }

    .activity-name {
      font-weight: 600;
    }

    .activity-status {
      font-size: var(--font-size-sm);
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
    }

    .activity-status.running {
      background: var(--kente-blue);
      color: white;
    }

    .activity-status.paused {
      background: var(--kente-orange);
      color: white;
    }

    .activity-status.planning {
      background: var(--color-border);
      color: var(--color-text);
    }

    .activity-meta {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }

    .empty-state {
      text-align: center;
      color: var(--color-text-muted);
      padding: var(--spacing-lg);
    }

    .message {
      padding: var(--spacing-md);
      border-radius: var(--border-radius-sm);
      margin-bottom: var(--spacing-md);
    }

    .message.success {
      background: color-mix(in srgb, var(--kente-green) 15%, transparent);
      border: 1px solid var(--kente-green);
    }

    .message.error {
      background: color-mix(in srgb, var(--kente-red) 15%, transparent);
      border: 1px solid var(--kente-red);
    }

    .attention-badge {
      background: var(--kente-orange);
      color: white;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
      font-weight: 600;
    }
  `;

  @state() private _brief: JorbBriefResponse | null = null;
  @state() private _loading = true;
  @state() private _error: string | null = null;
  @state() private _actionMessage: { type: 'success' | 'error'; text: string } | null = null;
  @state() private _approvalInputs: Map<string, string> = new Map();
  @state() private _actionInProgress: Set<string> = new Set();

  connectedCallback() {
    super.connectedCallback();
    this._fetchBrief();
  }

  private async _fetchBrief() {
    this._loading = true;
    this._error = null;

    try {
      // Don't update timestamp on initial fetch so we can see what's new
      this._brief = await api.getJorbsBrief({ update_timestamp: false });
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch briefing';
    } finally {
      this._loading = false;
    }
  }

  private async _markAsRead() {
    try {
      // Fetch again with update_timestamp: true to mark as read
      this._brief = await api.getJorbsBrief({ update_timestamp: true });
      this._actionMessage = { type: 'success', text: 'Briefing marked as read' };
      setTimeout(() => {
        this._actionMessage = null;
      }, 3000);
    } catch (err) {
      this._actionMessage = {
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to update briefing',
      };
    }
  }

  private _handleClose() {
    this.dispatchEvent(
      new CustomEvent('close', {
        bubbles: true,
        composed: true,
      })
    );
  }

  private _handleJorbSelect(jorbId: string) {
    this.dispatchEvent(
      new CustomEvent('jorb-select', {
        detail: { jorbId },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _handleApprovalInputChange(jorbId: string, e: Event) {
    const input = e.target as HTMLInputElement;
    this._approvalInputs = new Map([...this._approvalInputs, [jorbId, input.value]]);
  }

  private async _handleApprove(jorbId: string) {
    const decision = this._approvalInputs.get(jorbId) || 'Approved';
    this._actionInProgress = new Set([...this._actionInProgress, jorbId]);

    try {
      await api.approveJorb(jorbId, decision);
      this._actionMessage = { type: 'success', text: `Jorb approved` };
      this._approvalInputs.delete(jorbId);
      await this._fetchBrief();
    } catch (err) {
      this._actionMessage = {
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to approve jorb',
      };
    } finally {
      const newSet = new Set(this._actionInProgress);
      newSet.delete(jorbId);
      this._actionInProgress = newSet;
    }

    setTimeout(() => {
      this._actionMessage = null;
    }, 5000);
  }

  private async _handleCancel(jorbId: string) {
    this._actionInProgress = new Set([...this._actionInProgress, jorbId]);

    try {
      await api.cancelJorb(jorbId, 'Cancelled from briefing');
      this._actionMessage = { type: 'success', text: `Jorb cancelled` };
      await this._fetchBrief();
    } catch (err) {
      this._actionMessage = {
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to cancel jorb',
      };
    } finally {
      const newSet = new Set(this._actionInProgress);
      newSet.delete(jorbId);
      this._actionInProgress = newSet;
    }

    setTimeout(() => {
      this._actionMessage = null;
    }, 5000);
  }

  private _formatRelativeTime(isoDate: string): string {
    try {
      const date = new Date(isoDate);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);

      if (diffMins < 1) return 'just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      return date.toLocaleDateString();
    } catch {
      return isoDate;
    }
  }

  private _renderHighlights() {
    if (!this._brief || this._brief.highlights.length === 0) {
      return html`
        <div class="empty-state">No highlights since last briefing.</div>
      `;
    }

    return html`
      <div class="highlights">
        ${this._brief.highlights.map(
          highlight => html`<span class="highlight-item">${highlight}</span>`
        )}
      </div>
    `;
  }

  private _renderPendingDecisions() {
    if (!this._brief || this._brief.pending_decisions.length === 0) {
      return html`
        <div class="empty-state">No pending decisions.</div>
      `;
    }

    return html`
      <div class="pending-decisions">
        ${this._brief.pending_decisions.map(decision => this._renderDecisionItem(decision))}
      </div>
    `;
  }

  private _renderDecisionItem(decision: PendingDecision) {
    const isInProgress = this._actionInProgress.has(decision.jorb_id);

    return html`
      <div class="decision-item">
        <div class="decision-header">
          <span class="decision-name">${decision.name}</span>
          ${decision.needs_approval_for ? html`
            <span class="attention-badge">${decision.needs_approval_for}</span>
          ` : nothing}
        </div>
        ${decision.paused_reason ? html`
          <div class="decision-reason">${decision.paused_reason}</div>
        ` : nothing}
        <div class="decision-actions">
          <input
            type="text"
            class="approval-input"
            placeholder="Decision or instructions..."
            .value=${this._approvalInputs.get(decision.jorb_id) || ''}
            @input=${(e: Event) => this._handleApprovalInputChange(decision.jorb_id, e)}
          />
          <button
            class="button button-primary"
            @click=${() => this._handleApprove(decision.jorb_id)}
            ?disabled=${isInProgress}
          >
            ${isInProgress ? 'Processing...' : 'Approve'}
          </button>
          <button
            class="button button-danger"
            @click=${() => this._handleCancel(decision.jorb_id)}
            ?disabled=${isInProgress}
          >
            Cancel
          </button>
        </div>
      </div>
    `;
  }

  private _renderActivitySummary() {
    if (!this._brief || this._brief.activity_summary.length === 0) {
      return html`
        <div class="empty-state">No recent activity.</div>
      `;
    }

    return html`
      <div class="activity-list">
        ${this._brief.activity_summary.map(activity => this._renderActivityItem(activity))}
      </div>
    `;
  }

  private _renderActivityItem(activity: JorbActivitySummary) {
    return html`
      <div
        class="activity-item"
        @click=${() => this._handleJorbSelect(activity.jorb_id)}
      >
        <div class="activity-header">
          <span class="activity-name">${activity.name}</span>
          <span class="activity-status ${activity.status}">${activity.status}</span>
        </div>
        <div class="activity-meta">
          ${activity.message_count} messages
          ${activity.awaiting ? html` | Awaiting: ${activity.awaiting}` : nothing}
        </div>
      </div>
    `;
  }

  render() {
    if (this._loading) {
      return html`
        <div class="card">
          <div class="loading">
            <div class="spinner"></div>
            <span>Loading briefing...</span>
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

    if (!this._brief) {
      return nothing;
    }

    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Activity Briefing</h3>
          <div class="header-controls">
            ${this._brief.needs_attention > 0 ? html`
              <span class="attention-badge">${this._brief.needs_attention} need attention</span>
            ` : nothing}
            <button
              class="button button-primary"
              @click=${this._markAsRead}
            >
              Mark as Read
            </button>
            <button
              class="button button-secondary"
              @click=${this._handleClose}
              title="Close"
            >
              ✕
            </button>
          </div>
        </div>

        ${this._actionMessage ? html`
          <div class="message ${this._actionMessage.type}">${this._actionMessage.text}</div>
        ` : nothing}

        <div class="brief-meta">
          <span>Briefing time: ${this._formatRelativeTime(this._brief.briefing_time)}</span>
          <span>Since: ${this._formatRelativeTime(this._brief.since)}</span>
          <span>Open jorbs: ${this._brief.total_open_jorbs}</span>
          ${this._brief.recently_completed > 0 ? html`
            <span>Recently completed: ${this._brief.recently_completed}</span>
          ` : nothing}
        </div>

        <div class="section">
          <h4 class="section-title">Highlights</h4>
          ${this._renderHighlights()}
        </div>

        ${this._brief.pending_decisions.length > 0 ? html`
          <div class="section">
            <h4 class="section-title">Pending Decisions</h4>
            ${this._renderPendingDecisions()}
          </div>
        ` : nothing}

        <div class="section">
          <h4 class="section-title">Activity Summary</h4>
          ${this._renderActivitySummary()}
        </div>
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'jorbs-brief-view': JorbsBriefView;
  }
}
