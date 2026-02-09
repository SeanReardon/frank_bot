/**
 * Jorbs card component for Frank Bot dashboard.
 *
 * Displays list of jorbs (autonomous tasks) with status, contacts, and actions.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { Jorb, JorbMessage, JorbStatus } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

type StatusFilter = 'open' | 'closed' | 'all';

// Status badge colors
const STATUS_COLORS: Record<JorbStatus, { bg: string; text: string }> = {
  planning: { bg: 'var(--color-border)', text: 'var(--color-text)' },
  running: { bg: 'var(--kente-blue)', text: 'white' },
  paused: { bg: 'var(--kente-orange)', text: 'white' },
  complete: { bg: 'var(--kente-green)', text: 'white' },
  failed: { bg: 'var(--kente-red)', text: 'white' },
  cancelled: { bg: 'var(--color-border)', text: 'var(--color-text)' },
};

/**
 * Jorbs card component.
 *
 * @element jorbs-card
 * @fires jorb-select - Fired when a jorb is selected for detailed view
 */
@customElement('jorbs-card')
export class JorbsCard extends LitElement {
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
      /* Kente gold accent - jorbs are autonomous tasks, gold represents value/work */
      border-left: 3px solid var(--kente-gold);
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

    .button-icon {
      padding: var(--spacing-xs) var(--spacing-sm);
    }

    .button-sm {
      padding: var(--spacing-xs) var(--spacing-sm);
      font-size: var(--font-size-sm);
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

    .message.success {
      background: color-mix(in srgb, var(--kente-green) 15%, transparent);
      border: 1px solid var(--kente-green);
    }

    .empty-state {
      text-align: center;
      color: var(--color-text-muted);
      padding: var(--spacing-xl);
    }

    .jorbs-list {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .jorb-item {
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      overflow: hidden;
      border-left: 2px solid transparent;
      transition: border-color var(--transition-fast);
    }

    .jorb-item:hover {
      border-left-color: var(--kente-gold);
    }

    .jorb-item.paused {
      border-left-color: var(--kente-orange);
    }

    .jorb-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--spacing-md);
      cursor: pointer;
      transition: background var(--transition-fast);
      gap: var(--spacing-md);
    }

    .jorb-header:hover {
      background: var(--color-border);
    }

    .jorb-info {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: var(--spacing-xs);
    }

    .jorb-name-row {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
    }

    .jorb-name {
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

    .jorb-meta {
      display: flex;
      gap: var(--spacing-md);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      flex-wrap: wrap;
    }

    .expand-icon {
      transition: transform var(--transition-fast);
      color: var(--kente-gold);
    }

    .expand-icon.expanded {
      transform: rotate(180deg);
    }

    .jorb-details {
      padding: 0 var(--spacing-md) var(--spacing-md);
      border-top: 1px solid var(--color-border);
    }

    .jorb-details h4 {
      font-size: var(--font-size-sm);
      color: var(--kente-gold);
      margin: var(--spacing-md) 0 var(--spacing-sm);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .plan-block {
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      font-size: var(--font-size-sm);
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 200px;
      overflow-y: auto;
    }

    .contacts-list {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-sm);
    }

    .contact-tag {
      display: inline-flex;
      align-items: center;
      gap: var(--spacing-xs);
      padding: var(--spacing-xs) var(--spacing-sm);
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
    }

    .channel-icon {
      font-size: var(--font-size-sm);
    }

    .messages-preview {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-xs);
      max-height: 200px;
      overflow-y: auto;
    }

    .message-preview {
      padding: var(--spacing-sm);
      background: var(--color-bg);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
    }

    .message-preview.inbound {
      border-left: 2px solid var(--kente-blue);
    }

    .message-preview.outbound {
      border-left: 2px solid var(--kente-green);
    }

    .message-header {
      display: flex;
      justify-content: space-between;
      margin-bottom: var(--spacing-xs);
      color: var(--color-text-muted);
      font-size: var(--font-size-xs);
    }

    .progress-block {
      background: var(--color-bg);
      border: 1px solid var(--kente-green);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      font-size: var(--font-size-sm);
    }

    .paused-info {
      background: color-mix(in srgb, var(--kente-orange) 15%, transparent);
      border: 1px solid var(--kente-orange);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      margin-top: var(--spacing-md);
    }

    .paused-info h4 {
      color: var(--kente-orange);
      margin: 0 0 var(--spacing-sm);
    }

    .approval-form {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
      margin-top: var(--spacing-md);
    }

    .approval-form input {
      padding: var(--spacing-sm);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      background: var(--color-surface);
      color: var(--color-text);
      font-size: var(--font-size-base);
    }

    .approval-form input:focus {
      outline: none;
      border-color: var(--kente-gold);
    }

    .approval-buttons {
      display: flex;
      gap: var(--spacing-sm);
    }

    .view-thread-btn {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
      margin-top: var(--spacing-md);
    }

    .jorb-id {
      font-size: var(--font-size-xs);
      color: var(--color-text-muted);
      margin-top: var(--spacing-md);
    }

    .metrics-row {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-md);
      padding: var(--spacing-md);
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
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

    .metric-label {
      color: var(--color-text-muted);
    }

    .outcome-block {
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
    }

    .outcome-block.complete {
      border-color: var(--kente-green);
    }

    .outcome-block.failed {
      border-color: var(--kente-red);
    }

    .outcome-header {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      margin-bottom: var(--spacing-sm);
      font-weight: 600;
    }

    .outcome-header.complete {
      color: var(--kente-green);
    }

    .outcome-header.failed {
      color: var(--kente-red);
    }

    .outcome-content {
      font-size: var(--font-size-sm);
      white-space: pre-wrap;
    }
  `;

  @state() private _jorbs: Jorb[] = [];
  @state() private _loading = true;
  @state() private _error: string | null = null;
  @state() private _actionMessage: { type: 'success' | 'error'; text: string } | null = null;
  @state() private _expandedJorbId: string | null = null;
  @state() private _jorbMessages: Map<string, JorbMessage[]> = new Map();
  @state() private _loadingMessages: Set<string> = new Set();
  @state() private _statusFilter: StatusFilter = 'open';
  @state() private _autoRefresh = false;
  @state() private _approvalInput: Map<string, string> = new Map();
  @state() private _cancelInput: Map<string, string> = new Map();
  @state() private _actionInProgress: Set<string> = new Set();
  private _refreshInterval: number | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._fetchJorbs();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._stopAutoRefresh();
  }

  private async _fetchJorbs() {
    this._loading = true;
    this._error = null;

    try {
      const response = await api.getJorbs({ status: this._statusFilter });
      this._jorbs = response.jorbs ?? [];
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch jorbs';
    } finally {
      this._loading = false;
    }
  }

  private async _toggleExpand(jorbId: string) {
    if (this._expandedJorbId === jorbId) {
      this._expandedJorbId = null;
      return;
    }

    this._expandedJorbId = jorbId;

    // Load messages if not already loaded
    if (!this._jorbMessages.has(jorbId) && !this._loadingMessages.has(jorbId)) {
      await this._loadJorbMessages(jorbId);
    }
  }

  private async _loadJorbMessages(jorbId: string) {
    this._loadingMessages = new Set([...this._loadingMessages, jorbId]);

    try {
      const response = await api.getJorbMessages(jorbId, { limit: 10 });
      this._jorbMessages = new Map([...this._jorbMessages, [jorbId, response.messages]]);
    } catch (err) {
      console.error('Failed to load jorb messages:', err);
    } finally {
      const newSet = new Set(this._loadingMessages);
      newSet.delete(jorbId);
      this._loadingMessages = newSet;
    }
  }

  private _handleFilterChange(e: Event) {
    const select = e.target as HTMLSelectElement;
    this._statusFilter = select.value as StatusFilter;
    this._fetchJorbs();
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
      this._fetchJorbs();
    }, 10000); // Refresh every 10 seconds
  }

  private _stopAutoRefresh() {
    if (this._refreshInterval !== null) {
      window.clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
  }

  private async _handleApprove(jorbId: string) {
    const decision = this._approvalInput.get(jorbId) || 'Approved';
    this._actionInProgress = new Set([...this._actionInProgress, jorbId]);

    try {
      await api.approveJorb(jorbId, decision);
      this._actionMessage = { type: 'success', text: `Jorb ${jorbId} approved` };
      this._approvalInput.delete(jorbId);
      await this._fetchJorbs();
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

    // Clear message after 5 seconds
    setTimeout(() => {
      this._actionMessage = null;
    }, 5000);
  }

  private async _handleCancel(jorbId: string) {
    const reason = this._cancelInput.get(jorbId) || '';
    this._actionInProgress = new Set([...this._actionInProgress, jorbId]);

    try {
      await api.cancelJorb(jorbId, reason);
      this._actionMessage = { type: 'success', text: `Jorb ${jorbId} cancelled` };
      this._cancelInput.delete(jorbId);
      await this._fetchJorbs();
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

    // Clear message after 5 seconds
    setTimeout(() => {
      this._actionMessage = null;
    }, 5000);
  }

  private _handleApprovalInputChange(jorbId: string, e: Event) {
    const input = e.target as HTMLInputElement;
    this._approvalInput = new Map([...this._approvalInput, [jorbId, input.value]]);
  }

  private _handleCancelInputChange(jorbId: string, e: Event) {
    const input = e.target as HTMLInputElement;
    this._cancelInput = new Map([...this._cancelInput, [jorbId, input.value]]);
  }

  private _handleViewThread(jorbId: string) {
    // Dispatch event for parent to handle navigation to thread view
    this.dispatchEvent(
      new CustomEvent('jorb-select', {
        detail: { jorbId },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _formatDate(isoDate: string): string {
    try {
      const date = new Date(isoDate);
      return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoDate;
    }
  }

  private _formatRelativeTime(isoDate: string): string {
    try {
      const date = new Date(isoDate);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffMins < 1) return 'just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return this._formatDate(isoDate);
    } catch {
      return isoDate;
    }
  }

  private _formatTokens(tokens: number): string {
    if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`;
    if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
    return tokens.toString();
  }

  private _formatCost(cost: number): string {
    if (cost === 0) return '$0.00';
    if (cost < 0.01) return '<$0.01';
    return `$${cost.toFixed(2)}`;
  }

  private _getChannelIcon(channel: string): string {
    switch (channel) {
      case 'telegram':
        return '✈️';
      case 'sms':
        return '💬';
      case 'email':
        return '📧';
      default:
        return '📨';
    }
  }

  private _getStatusStyle(status: JorbStatus): string {
    const colors = STATUS_COLORS[status] || STATUS_COLORS.planning;
    return `background: ${colors.bg}; color: ${colors.text};`;
  }

  private _renderContent() {
    if (this._loading && this._jorbs.length === 0) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading jorbs...</span>
        </div>
      `;
    }

    if (this._error) {
      return html`
        <div class="message error">${this._error}</div>
      `;
    }

    if (this._jorbs.length === 0) {
      return html`
        <div class="empty-state">
          <p>No jorbs found${this._statusFilter !== 'all' ? ` with status "${this._statusFilter}"` : ''}.</p>
          <p>Jorbs are autonomous tasks created via the /jorbs/create endpoint.</p>
        </div>
      `;
    }

    return html`
      <div class="jorbs-list">
        ${this._jorbs.map(jorb => this._renderJorb(jorb))}
      </div>
    `;
  }

  private _renderJorb(jorb: Jorb) {
    const isExpanded = this._expandedJorbId === jorb.jorb_id;
    const messages = this._jorbMessages.get(jorb.jorb_id);
    const isLoadingMessages = this._loadingMessages.has(jorb.jorb_id);
    const isActionInProgress = this._actionInProgress.has(jorb.jorb_id);
    const contacts = jorb.contacts ?? [];

    return html`
      <div class="jorb-item ${jorb.status === 'paused' ? 'paused' : ''}">
        <div
          class="jorb-header"
          @click=${() => this._toggleExpand(jorb.jorb_id)}
          role="button"
          tabindex="0"
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              this._toggleExpand(jorb.jorb_id);
            }
          }}
        >
          <div class="jorb-info">
            <div class="jorb-name-row">
              <span class="jorb-name">${jorb.name}</span>
              <span class="status-badge" style=${this._getStatusStyle(jorb.status)}>${jorb.status}</span>
            </div>
            <div class="jorb-meta">
              <span title="Last updated">${this._formatRelativeTime(jorb.updated_at)}</span>
              <span title="Contacts">${contacts.length} contact${contacts.length !== 1 ? 's' : ''}</span>
              ${jorb.awaiting ? html`<span title="Awaiting">⏳ ${jorb.awaiting}</span>` : nothing}
            </div>
          </div>
          <span class="expand-icon ${isExpanded ? 'expanded' : ''}">▼</span>
        </div>

        ${isExpanded ? html`
          <div class="jorb-details">
            ${jorb.status === 'paused' ? this._renderPausedInfo(jorb, isActionInProgress) : nothing}

            <h4>Plan</h4>
            <div class="plan-block">${jorb.original_plan}</div>

            ${jorb.progress_summary ? html`
              <h4>Progress</h4>
              <div class="progress-block">${jorb.progress_summary}</div>
            ` : nothing}

            ${jorb.outcome ? html`
              <h4>Outcome</h4>
              <div class="outcome-block ${jorb.status}">
                <div class="outcome-header ${jorb.status}">
                  ${jorb.status === 'complete' ? '✓ Completed' : '✗ Failed'}
                  ${jorb.outcome.completed_at ? html`
                    <span style="font-weight: normal; color: var(--color-text-muted);">
                      ${this._formatRelativeTime(jorb.outcome.completed_at)}
                    </span>
                  ` : nothing}
                </div>
                ${jorb.outcome.result ? html`
                  <div class="outcome-content">${jorb.outcome.result}</div>
                ` : nothing}
                ${jorb.outcome.failure_reason ? html`
                  <div class="outcome-content" style="color: var(--kente-red);">
                    ${jorb.outcome.failure_reason}
                  </div>
                ` : nothing}
              </div>
            ` : nothing}

            <h4>Metrics</h4>
            <div class="metrics-row">
              <div class="metric-item">
                <span class="metric-value">${jorb.metrics.messages_in}</span>
                <span class="metric-label">in</span>
              </div>
              <div class="metric-item">
                <span class="metric-value">${jorb.metrics.messages_out}</span>
                <span class="metric-label">out</span>
              </div>
              <div class="metric-item">
                <span class="metric-value">${this._formatTokens(jorb.metrics.tokens_used)}</span>
                <span class="metric-label">tokens</span>
              </div>
              <div class="metric-item">
                <span class="metric-value">${this._formatCost(jorb.metrics.estimated_cost)}</span>
                <span class="metric-label">cost</span>
              </div>
              ${jorb.metrics.context_resets > 0 ? html`
                <div class="metric-item">
                  <span class="metric-value">${jorb.metrics.context_resets}</span>
                  <span class="metric-label">resets</span>
                </div>
              ` : nothing}
            </div>

            <h4>Contacts</h4>
            <div class="contacts-list">
              ${contacts.length > 0 ? contacts.map(contact => html`
                <span class="contact-tag">
                  <span class="channel-icon">${this._getChannelIcon(contact.channel)}</span>
                  ${contact.name || contact.identifier}
                </span>
              `) : html`<span class="contact-tag">No contacts</span>`}
            </div>

            <h4>Recent Messages</h4>
            ${isLoadingMessages ? html`
              <div class="loading">
                <div class="spinner"></div>
                <span>Loading messages...</span>
              </div>
            ` : messages && messages.length > 0 ? html`
              <div class="messages-preview">
                ${messages.slice(-5).map(msg => html`
                  <div class="message-preview ${msg.direction}">
                    <div class="message-header">
                      <span>${this._getChannelIcon(msg.channel)} ${msg.sender_name || msg.sender || 'System'}</span>
                      <span>${this._formatRelativeTime(msg.timestamp)}</span>
                    </div>
                    <div>${msg.content.length > 100 ? msg.content.substring(0, 100) + '...' : msg.content}</div>
                  </div>
                `)}
              </div>
              <button
                class="button button-secondary button-sm view-thread-btn"
                @click=${(e: Event) => {
                  e.stopPropagation();
                  this._handleViewThread(jorb.jorb_id);
                }}
              >
                View Full Thread →
              </button>
            ` : html`
              <p style="color: var(--color-text-muted); font-size: var(--font-size-sm);">No messages yet.</p>
            `}

            <div class="jorb-id">
              <strong>Jorb ID:</strong> ${jorb.jorb_id}<br>
              <strong>Created:</strong> ${this._formatDate(jorb.created_at)}
            </div>
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _renderPausedInfo(jorb: Jorb, isActionInProgress: boolean) {
    return html`
      <div class="paused-info">
        <h4>⚠️ Paused - Action Required</h4>
        <p><strong>Reason:</strong> ${jorb.paused_reason || 'Not specified'}</p>
        ${jorb.needs_approval_for ? html`
          <p><strong>Needs approval for:</strong> ${jorb.needs_approval_for}</p>
        ` : nothing}

        <div class="approval-form">
          <input
            type="text"
            placeholder="Decision or instructions..."
            .value=${this._approvalInput.get(jorb.jorb_id) || ''}
            @input=${(e: Event) => this._handleApprovalInputChange(jorb.jorb_id, e)}
            @click=${(e: Event) => e.stopPropagation()}
          />
          <div class="approval-buttons">
            <button
              class="button button-primary button-sm"
              @click=${(e: Event) => {
                e.stopPropagation();
                this._handleApprove(jorb.jorb_id);
              }}
              ?disabled=${isActionInProgress}
            >
              ${isActionInProgress ? 'Approving...' : 'Approve'}
            </button>
            <button
              class="button button-danger button-sm"
              @click=${(e: Event) => {
                e.stopPropagation();
                this._handleCancel(jorb.jorb_id);
              }}
              ?disabled=${isActionInProgress}
            >
              ${isActionInProgress ? 'Cancelling...' : 'Cancel Jorb'}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  render() {
    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Jorbs</h3>
          <div class="header-controls">
            <select
              class="filter-select"
              @change=${this._handleFilterChange}
              .value=${this._statusFilter}
            >
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="all">All</option>
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
              @click=${this._fetchJorbs}
              ?disabled=${this._loading}
              title="Refresh"
            >
              ↻
            </button>
          </div>
        </div>
        ${this._actionMessage ? html`
          <div class="message ${this._actionMessage.type}">${this._actionMessage.text}</div>
        ` : nothing}
        ${this._renderContent()}
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'jorbs-card': JorbsCard;
  }
}
