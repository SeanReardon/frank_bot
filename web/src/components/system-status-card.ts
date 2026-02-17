/**
 * System Status card component for Frank Bot dashboard.
 *
 * Displays the health and status of Frank Bot's orchestration machinery:
 * - Switchboard (message routing)
 * - Agent Runner (LLM execution)
 * - Telegram Router (incoming message handling)
 * - Message Buffer (debouncing)
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { SystemStatusResponse, AndroidPhoneStatus } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

/**
 * System Status card component.
 *
 * @element system-status-card
 */
@customElement('system-status-card')
export class SystemStatusCard extends LitElement {
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
      /* Blue accent - represents the system/infrastructure */
      border-left: 3px solid var(--kente-blue);
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
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
    }

    .health-indicator {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
    }

    .health-indicator.healthy {
      background: var(--kente-green);
      box-shadow: 0 0 6px var(--kente-green);
    }

    .health-indicator.unhealthy {
      background: var(--kente-orange);
      box-shadow: 0 0 6px var(--kente-orange);
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
      margin-bottom: var(--spacing-md);
    }

    .message.error {
      background: color-mix(in srgb, var(--kente-red) 15%, transparent);
      border: 1px solid var(--kente-red);
    }

    .components-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: var(--spacing-md);
    }

    .component-card {
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      border-left: 2px solid var(--color-border);
    }

    .component-card.configured {
      border-left-color: var(--kente-green);
    }

    .component-card.not-configured {
      border-left-color: var(--kente-orange);
    }

    .component-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: var(--spacing-sm);
    }

    .component-name {
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
    }

    .component-icon {
      font-size: var(--font-size-lg);
    }

    .status-badge {
      display: inline-block;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-xs);
      font-weight: 500;
    }

    .status-badge.success {
      background: var(--kente-green);
      color: white;
    }

    .status-badge.warning {
      background: var(--kente-orange);
      color: white;
    }

    .component-description {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      margin-bottom: var(--spacing-sm);
    }

    .component-details {
      font-size: var(--font-size-sm);
      display: flex;
      flex-direction: column;
      gap: var(--spacing-xs);
    }

    .detail-item {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
    }

    .detail-label {
      color: var(--color-text-muted);
    }

    .detail-value {
      font-family: monospace;
      color: var(--color-text);
    }

    .jorbs-summary {
      margin-top: var(--spacing-md);
      padding: var(--spacing-md);
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      border-left: 2px solid var(--kente-gold);
    }

    .jorbs-summary h4 {
      margin: 0 0 var(--spacing-sm);
      font-size: var(--font-size-base);
      color: var(--kente-gold-light);
    }

    .jorbs-stats {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-md);
      font-size: var(--font-size-sm);
    }

    .jorb-stat {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
    }

    .jorb-stat-value {
      font-weight: 600;
      font-size: var(--font-size-lg);
    }

    .jorb-stat-label {
      color: var(--color-text-muted);
    }

    .needs-attention {
      color: var(--kente-orange);
    }

    .phone-section {
      margin-top: var(--spacing-md);
      padding: var(--spacing-md);
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      border-left: 2px solid var(--kente-blue);
    }

    .phone-section.disconnected {
      border-left-color: var(--kente-orange);
    }

    .phone-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: var(--spacing-sm);
    }

    .phone-header h4 {
      margin: 0;
      font-size: var(--font-size-base);
      color: var(--kente-gold-light);
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
    }

    .phone-stats {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-md);
      font-size: var(--font-size-sm);
    }

    .phone-stat {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
    }

    .phone-stat-value {
      font-weight: 600;
    }

    .phone-stat-label {
      color: var(--color-text-muted);
    }

    .phone-error {
      font-size: var(--font-size-sm);
      color: var(--kente-orange);
      margin-top: var(--spacing-xs);
    }

    .battery-good { color: var(--kente-green); }
    .battery-mid { color: var(--kente-orange); }
    .battery-low { color: var(--kente-red); }
  `;

  @state() private _status: SystemStatusResponse | null = null;
  @state() private _loading = true;
  @state() private _refreshing = false;
  @state() private _error: string | null = null;
  private _refreshInterval: number | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._fetchStatus();
    // Auto-refresh every 60 seconds
    this._refreshInterval = window.setInterval(() => {
      this._fetchStatus();
    }, 60000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refreshInterval !== null) {
      window.clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
  }

  private async _fetchStatus() {
    const isInitialLoad = this._status === null && this._error === null;
    if (isInitialLoad) {
      this._loading = true;
    } else {
      this._refreshing = true;
    }

    try {
      this._status = await api.getSystemStatus();
      this._error = null;
    } catch (err) {
      // Only set error when no stale data is available
      if (!this._status) {
        this._error = err instanceof Error ? err.message : 'Failed to fetch system status';
      }
    } finally {
      this._loading = false;
      this._refreshing = false;
    }
  }

  private _renderComponent(
    icon: string,
    name: string,
    configured: boolean,
    description: string,
    details: Array<{ label: string; value: string }>
  ) {
    return html`
      <div class="component-card ${configured ? 'configured' : 'not-configured'}">
        <div class="component-header">
          <span class="component-name">
            <span class="component-icon">${icon}</span>
            ${name}
          </span>
          <span class="status-badge ${configured ? 'success' : 'warning'}">
            ${configured ? '✓ Ready' : '⚠ Not configured'}
          </span>
        </div>
        <div class="component-description">${description}</div>
        <div class="component-details">
          ${details.map(d => html`
            <div class="detail-item">
              <span class="detail-label">${d.label}:</span>
              <span class="detail-value">${d.value}</span>
            </div>
          `)}
        </div>
      </div>
    `;
  }

  private _getBatteryClass(level: number | null | undefined): string {
    if (level === null || level === undefined) return '';
    if (level > 50) return 'battery-good';
    if (level > 20) return 'battery-mid';
    return 'battery-low';
  }

  private _getTransportLabel(transport?: string): string {
    if (transport === 'usb') return 'USB';
    if (transport === 'tcp') return 'WiFi';
    return 'Unknown';
  }

  private _renderPhone(phone: AndroidPhoneStatus) {
    const connected = phone.connected;
    const transport = phone.transport || 'tcp';
    const transportLabel = this._getTransportLabel(transport);

    return html`
      <div class="phone-section ${connected ? '' : 'disconnected'}">
        <div class="phone-header">
          <h4>
            📱 Android Phone
            <span class="status-badge ${connected ? 'success' : 'warning'}">
              ${connected ? `✓ ${transportLabel}` : '✗ Offline'}
            </span>
          </h4>
        </div>
        ${connected ? html`
          <div class="phone-stats">
            ${phone.device_model ? html`
              <div class="phone-stat">
                <span class="phone-stat-label">Device:</span>
                <span class="phone-stat-value">${phone.device_model}</span>
              </div>
            ` : nothing}
            ${phone.android_version ? html`
              <div class="phone-stat">
                <span class="phone-stat-label">Android:</span>
                <span class="phone-stat-value">${phone.android_version}</span>
              </div>
            ` : nothing}
            ${phone.battery_level !== null && phone.battery_level !== undefined ? html`
              <div class="phone-stat">
                <span class="phone-stat-label">Battery:</span>
                <span class="phone-stat-value ${this._getBatteryClass(phone.battery_level)}">
                  ${phone.battery_level}%
                </span>
              </div>
            ` : nothing}
            <div class="phone-stat">
              <span class="phone-stat-label">WiFi:</span>
              <span class="phone-stat-value">
                ${phone.wifi_enabled === false ? 'Off' : phone.wifi_ssid || 'On'}
              </span>
            </div>
          </div>
        ` : html`
          ${phone.error ? html`
            <div class="phone-error">${phone.error}</div>
          ` : nothing}
        `}
      </div>
    `;
  }

  private _renderContent() {
    if (this._loading) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading system status...</span>
        </div>
      `;
    }

    if (this._error) {
      return html`
        <div class="message error">${this._error}</div>
      `;
    }

    if (!this._status) {
      return html`
        <div class="message error">No status data available</div>
      `;
    }

    const { switchboard, agent_runner, telegram_router, message_buffer, jorbs } = this._status;

    return html`
      <div class="components-grid">
        ${this._renderComponent(
          '📡',
          'Switchboard',
          switchboard.configured,
          switchboard.description,
          [{ label: 'Model', value: switchboard.model || 'N/A' }]
        )}

        ${this._renderComponent(
          '🤖',
          'Agent Runner',
          agent_runner.configured,
          agent_runner.description,
          [{ label: 'Model', value: agent_runner.model || 'N/A' }]
        )}

        ${this._renderComponent(
          '✈️',
          'Telegram Router',
          telegram_router.initialized || false,
          telegram_router.description,
          [
            { label: 'Telegram', value: telegram_router.telegram_configured ? 'Connected' : 'Not connected' },
            { label: 'Agent', value: telegram_router.agent_configured ? 'Ready' : 'Not ready' },
          ]
        )}

        ${this._renderComponent(
          '📨',
          'Message Buffer',
          true, // Buffer is always "configured"
          message_buffer.description,
          [
            { label: 'Pending', value: String(message_buffer.pending_messages || 0) },
            { label: 'Telegram debounce', value: `${message_buffer.debounce_telegram_seconds}s` },
            { label: 'SMS debounce', value: `${message_buffer.debounce_sms_seconds}s` },
          ]
        )}
      </div>

      ${this._status.android_phone ? this._renderPhone(this._status.android_phone) : nothing}

      <div class="jorbs-summary">
        <h4>📋 Active Jorbs</h4>
        <div class="jorbs-stats">
          <div class="jorb-stat">
            <span class="jorb-stat-value">${jorbs.total_open}</span>
            <span class="jorb-stat-label">open</span>
          </div>
          <div class="jorb-stat">
            <span class="jorb-stat-value">${jorbs.by_status.running}</span>
            <span class="jorb-stat-label">running</span>
          </div>
          <div class="jorb-stat">
            <span class="jorb-stat-value">${jorbs.by_status.planning}</span>
            <span class="jorb-stat-label">planning</span>
          </div>
          <div class="jorb-stat ${jorbs.needs_attention > 0 ? 'needs-attention' : ''}">
            <span class="jorb-stat-value">${jorbs.needs_attention}</span>
            <span class="jorb-stat-label">need attention</span>
          </div>
        </div>
      </div>
    `;
  }

  render() {
    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">
            <span class="health-indicator ${this._status?.healthy ? 'healthy' : 'unhealthy'}"></span>
            System Status
            ${this._refreshing ? html`<span style="opacity:0.35;font-size:0.7em">↻</span>` : nothing}
          </h3>
          <button
            class="button button-secondary button-icon"
            @click=${this._fetchStatus}
            ?disabled=${this._loading || this._refreshing}
            title="Refresh"
          >
            ↻
          </button>
        </div>
        ${this._renderContent()}
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'system-status-card': SystemStatusCard;
  }
}
