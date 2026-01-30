/**
 * Telegram Bot card component for Frank Bot dashboard.
 *
 * Displays the configuration status of the Telegram Bot notification service
 * and provides a test connection button.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { TelegramBotStatus, TelegramBotTestResponse } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

/**
 * Telegram Bot card component.
 *
 * @element telegram-bot-card
 */
@customElement('telegram-bot-card')
export class TelegramBotCard extends LitElement {
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
      /* Kente blue left accent for notifications */
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
    }

    .status-badge {
      display: inline-block;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
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

    .status-badge.error {
      background: var(--kente-red);
      color: white;
    }

    .status-badge.neutral {
      background: var(--color-border);
      color: var(--color-text);
    }

    .card-content {
      color: var(--color-text);
    }

    .config-info {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .config-row {
      display: flex;
      gap: var(--spacing-sm);
    }

    .config-label {
      color: var(--color-text-muted);
      min-width: 80px;
    }

    .config-value {
      font-weight: 500;
      font-family: monospace;
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
      color: var(--kente-black);
    }

    .button-primary:hover:not(:disabled) {
      background: var(--kente-gold-light);
      box-shadow: 0 2px 8px rgba(218, 165, 32, 0.3);
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

    .button-row {
      display: flex;
      gap: var(--spacing-sm);
      margin-top: var(--spacing-md);
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

    .message.info {
      background: color-mix(in srgb, var(--kente-blue) 15%, transparent);
      border: 1px solid var(--kente-blue);
    }

    .message.error {
      background: color-mix(in srgb, var(--kente-red) 15%, transparent);
      border: 1px solid var(--kente-red);
    }

    .message.success {
      background: color-mix(in srgb, var(--kente-green) 15%, transparent);
      border: 1px solid var(--kente-green);
    }

    .description {
      color: var(--color-text-muted);
      font-size: var(--font-size-sm);
      margin-bottom: var(--spacing-md);
    }
  `;

  @state() private _status: TelegramBotStatus | null = null;
  @state() private _loading = true;
  @state() private _testing = false;
  @state() private _testResult: TelegramBotTestResponse | null = null;
  @state() private _error: string | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._fetchStatus();
  }

  private async _fetchStatus() {
    this._loading = true;
    this._error = null;

    try {
      this._status = await api.getTelegramBotStatus();
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch status';
    } finally {
      this._loading = false;
    }
  }

  private async _testConnection() {
    this._testing = true;
    this._testResult = null;
    this._error = null;

    try {
      this._testResult = await api.testTelegramBot();
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Test failed';
    } finally {
      this._testing = false;
    }
  }

  private _getStatusBadge() {
    if (this._loading) {
      return html`<span class="status-badge neutral">Loading...</span>`;
    }

    if (!this._status) {
      return html`<span class="status-badge error">Error</span>`;
    }

    if (this._status.configured) {
      return html`<span class="status-badge success">Configured</span>`;
    } else {
      return html`<span class="status-badge error">Not Configured</span>`;
    }
  }

  private _renderContent() {
    if (this._loading) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading Telegram Bot status...</span>
        </div>
      `;
    }

    if (this._error && !this._status) {
      return html`
        <div class="message error">${this._error}</div>
        <div class="button-row">
          <button class="button button-secondary" @click=${this._fetchStatus}>
            Retry
          </button>
        </div>
      `;
    }

    if (!this._status) {
      return html`<div class="message error">Unable to load status</div>`;
    }

    if (!this._status.configured) {
      return this._renderNotConfigured();
    }

    return this._renderConfigured();
  }

  private _renderNotConfigured() {
    return html`
      <div class="message info">
        Telegram Bot notifications are not configured. Please set the following environment variables:
        <ul>
          <li><code>TELEGRAM_BOT_TOKEN</code></li>
          <li><code>TELEGRAM_BOT_CHAT_ID</code></li>
        </ul>
      </div>
    `;
  }

  private _renderConfigured() {
    return html`
      <p class="description">
        Used for sending notifications about SMS messages from unknown senders.
      </p>

      <div class="config-info">
        <div class="config-row">
          <span class="config-label">Chat ID:</span>
          <span class="config-value">${this._status?.chatId || 'Unknown'}</span>
        </div>
      </div>

      <div class="button-row">
        <button
          class="button button-secondary"
          @click=${this._testConnection}
          ?disabled=${this._testing}
        >
          ${this._testing ? 'Testing...' : 'Test Connection'}
        </button>
      </div>

      ${this._renderTestResult()}
      ${this._error ? html`<div class="message error">${this._error}</div>` : nothing}
    `;
  }

  private _renderTestResult() {
    if (!this._testResult) return nothing;

    if (this._testResult.success) {
      return html`
        <div class="message success">
          Test notification sent successfully! Check your Telegram chat.
        </div>
      `;
    }

    return html`
      <div class="message error">
        Test failed: ${this._testResult.error || 'Unknown error'}
      </div>
    `;
  }

  render() {
    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Telegram Bot Notifications</h3>
          ${this._getStatusBadge()}
        </div>
        <div class="card-content">
          ${this._renderContent()}
        </div>
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'telegram-bot-card': TelegramBotCard;
  }
}
