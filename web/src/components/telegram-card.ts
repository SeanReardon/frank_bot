/**
 * Telegram card component for Frank Bot dashboard.
 *
 * Displays Telegram connection status and provides auth wizard.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { TelegramStatus, TelegramTestResponse } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

type AuthWizardStep = 'idle' | 'sending_code' | 'enter_code' | 'verifying_code' | 'enter_2fa' | 'verifying_2fa';

/**
 * Telegram card component.
 *
 * @element telegram-card
 */
@customElement('telegram-card')
export class TelegramCard extends LitElement {
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
      /* Kente gold left accent */
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

    .account-info {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .account-row {
      display: flex;
      gap: var(--spacing-sm);
    }

    .account-label {
      color: var(--color-text-muted);
      min-width: 80px;
    }

    .account-value {
      font-weight: 500;
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
      background: color-mix(in srgb, var(--kente-gold) 15%, transparent);
      border: 1px solid var(--kente-gold-dark);
    }

    .message.error {
      background: color-mix(in srgb, var(--kente-red) 15%, transparent);
      border: 1px solid var(--kente-red);
    }

    .message.success {
      background: color-mix(in srgb, var(--kente-green) 15%, transparent);
      border: 1px solid var(--kente-green);
    }

    .test-result {
      margin-top: var(--spacing-md);
      padding: var(--spacing-md);
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      border-left: 2px solid var(--kente-green);
    }

    .test-result h4 {
      margin: 0 0 var(--spacing-sm) 0;
      font-size: var(--font-size-base);
      color: var(--kente-green);
    }

    .test-result ul {
      margin: 0;
      padding-left: var(--spacing-lg);
    }

    .test-result li {
      margin-bottom: var(--spacing-xs);
    }

    .wizard {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-md);
    }

    .wizard-step {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .wizard-step label {
      font-weight: 500;
      color: var(--kente-gold-light);
    }

    .input {
      padding: var(--spacing-sm) var(--spacing-md);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      background: var(--color-bg);
      color: var(--color-text);
      font-size: var(--font-size-base);
      font-family: inherit;
    }

    .input:focus {
      outline: none;
      border-color: var(--kente-gold);
      box-shadow: 0 0 0 2px rgba(218, 165, 32, 0.2);
    }

    .input::placeholder {
      color: var(--color-text-muted);
    }

    .wizard-description {
      color: var(--color-text-muted);
      font-size: var(--font-size-sm);
    }
  `;

  @state() private _status: TelegramStatus | null = null;
  @state() private _loading = true;
  @state() private _testing = false;
  @state() private _testResult: TelegramTestResponse | null = null;
  @state() private _error: string | null = null;

  // Auth wizard state
  @state() private _authStep: AuthWizardStep = 'idle';
  @state() private _phoneCodeHash: string | null = null;
  @state() private _verificationCode = '';
  @state() private _twoFactorPassword = '';
  @state() private _authError: string | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._fetchStatus();
  }

  private async _fetchStatus() {
    this._loading = true;
    this._error = null;

    try {
      this._status = await api.getTelegramStatus();
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
      this._testResult = await api.testTelegramConnection();
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Test failed';
    } finally {
      this._testing = false;
    }
  }

  private async _startAuth() {
    this._authStep = 'sending_code';
    this._authError = null;

    try {
      const result = await api.startTelegramAuth();

      if (result.status === 'already_authorized') {
        // Already authorized, refresh status
        this._authStep = 'idle';
        await this._fetchStatus();
        return;
      }

      if (result.status === 'code_sent' && result.phoneCodeHash) {
        this._phoneCodeHash = result.phoneCodeHash;
        this._authStep = 'enter_code';
      } else if (result.status === 'error') {
        this._authError = result.error || 'Failed to send verification code';
        this._authStep = 'idle';
      }
    } catch (err) {
      this._authError = err instanceof Error ? err.message : 'Failed to start authentication';
      this._authStep = 'idle';
    }
  }

  private async _verifyCode() {
    if (!this._phoneCodeHash || !this._verificationCode) return;

    this._authStep = 'verifying_code';
    this._authError = null;

    try {
      const result = await api.verifyTelegramCode(
        this._verificationCode,
        this._phoneCodeHash
      );

      if (result.status === 'success') {
        // Successfully authenticated
        this._resetAuthWizard();
        await this._fetchStatus();
      } else if (result.status === 'needs_2fa') {
        // 2FA required
        this._authStep = 'enter_2fa';
      } else if (result.status === 'invalid_code') {
        this._authError = 'Invalid verification code. Please try again.';
        this._authStep = 'enter_code';
        this._verificationCode = '';
      } else {
        this._authError = result.error || 'Verification failed';
        this._authStep = 'enter_code';
      }
    } catch (err) {
      this._authError = err instanceof Error ? err.message : 'Verification failed';
      this._authStep = 'enter_code';
    }
  }

  private async _submit2FA() {
    if (!this._twoFactorPassword) return;

    this._authStep = 'verifying_2fa';
    this._authError = null;

    try {
      const result = await api.submitTelegram2FA(this._twoFactorPassword);

      if (result.status === 'success') {
        // Successfully authenticated
        this._resetAuthWizard();
        await this._fetchStatus();
      } else if (result.status === 'invalid_password') {
        this._authError = 'Invalid password. Please try again.';
        this._authStep = 'enter_2fa';
        this._twoFactorPassword = '';
      } else {
        this._authError = result.error || '2FA verification failed';
        this._authStep = 'enter_2fa';
      }
    } catch (err) {
      this._authError = err instanceof Error ? err.message : '2FA verification failed';
      this._authStep = 'enter_2fa';
    }
  }

  private _resetAuthWizard() {
    this._authStep = 'idle';
    this._phoneCodeHash = null;
    this._verificationCode = '';
    this._twoFactorPassword = '';
    this._authError = null;
  }

  private _cancelAuth() {
    this._resetAuthWizard();
  }

  private _handleCodeInput(e: InputEvent) {
    this._verificationCode = (e.target as HTMLInputElement).value;
  }

  private _handlePasswordInput(e: InputEvent) {
    this._twoFactorPassword = (e.target as HTMLInputElement).value;
  }

  private _handleCodeKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && this._verificationCode) {
      this._verifyCode();
    }
  }

  private _handlePasswordKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && this._twoFactorPassword) {
      this._submit2FA();
    }
  }

  private _getStatusBadge() {
    if (this._loading) {
      return html`<span class="status-badge neutral">Loading...</span>`;
    }

    if (!this._status) {
      return html`<span class="status-badge error">Error</span>`;
    }

    // Show "Authenticating" badge during auth flow
    if (this._authStep !== 'idle') {
      return html`<span class="status-badge warning">Authenticating...</span>`;
    }

    switch (this._status.status) {
      case 'connected':
        return html`<span class="status-badge success">Connected</span>`;
      case 'needs_auth':
        return html`<span class="status-badge warning">Needs Auth</span>`;
      case 'not_configured':
        return html`<span class="status-badge error">Not Configured</span>`;
      default:
        return html`<span class="status-badge neutral">Unknown</span>`;
    }
  }

  private _renderContent() {
    if (this._loading) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading Telegram status...</span>
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

    // If auth wizard is active, show it
    if (this._authStep !== 'idle') {
      return this._renderAuthWizard();
    }

    switch (this._status.status) {
      case 'not_configured':
        return this._renderNotConfigured();
      case 'needs_auth':
        return this._renderNeedsAuth();
      case 'connected':
        return this._renderConnected();
      default:
        return html`<div class="message error">Unknown status</div>`;
    }
  }

  private _renderNotConfigured() {
    return html`
      <div class="message info">
        Telegram is not configured. Please set the following environment variables:
        <ul>
          <li><code>TELEGRAM_API_ID</code></li>
          <li><code>TELEGRAM_API_HASH</code></li>
          <li><code>TELEGRAM_PHONE</code></li>
        </ul>
      </div>
    `;
  }

  private _renderNeedsAuth() {
    return html`
      <p>Telegram credentials are configured but authentication is required.</p>
      ${this._authError ? html`<div class="message error">${this._authError}</div>` : nothing}
      <div class="button-row">
        <button class="button button-primary" @click=${this._startAuth}>
          Connect Telegram
        </button>
      </div>
    `;
  }

  private _renderAuthWizard() {
    switch (this._authStep) {
      case 'sending_code':
        return html`
          <div class="wizard">
            <div class="loading">
              <div class="spinner"></div>
              <span>Sending verification code...</span>
            </div>
          </div>
        `;

      case 'enter_code':
        return html`
          <div class="wizard">
            <p class="wizard-description">
              A verification code has been sent to your Telegram app or via SMS.
              Please enter the code below.
            </p>
            ${this._authError ? html`<div class="message error">${this._authError}</div>` : nothing}
            <div class="wizard-step">
              <label for="verification-code">Verification Code</label>
              <input
                id="verification-code"
                type="text"
                class="input"
                placeholder="12345"
                .value=${this._verificationCode}
                @input=${this._handleCodeInput}
                @keydown=${this._handleCodeKeydown}
                autocomplete="one-time-code"
              />
            </div>
            <div class="button-row">
              <button
                class="button button-primary"
                @click=${this._verifyCode}
                ?disabled=${!this._verificationCode}
              >
                Verify Code
              </button>
              <button class="button button-secondary" @click=${this._cancelAuth}>
                Cancel
              </button>
            </div>
          </div>
        `;

      case 'verifying_code':
        return html`
          <div class="wizard">
            <div class="loading">
              <div class="spinner"></div>
              <span>Verifying code...</span>
            </div>
          </div>
        `;

      case 'enter_2fa':
        return html`
          <div class="wizard">
            <p class="wizard-description">
              Your account has two-factor authentication enabled.
              Please enter your 2FA password.
            </p>
            ${this._authError ? html`<div class="message error">${this._authError}</div>` : nothing}
            <div class="wizard-step">
              <label for="two-factor-password">2FA Password</label>
              <input
                id="two-factor-password"
                type="password"
                class="input"
                placeholder="Enter your 2FA password"
                .value=${this._twoFactorPassword}
                @input=${this._handlePasswordInput}
                @keydown=${this._handlePasswordKeydown}
                autocomplete="current-password"
              />
            </div>
            <div class="button-row">
              <button
                class="button button-primary"
                @click=${this._submit2FA}
                ?disabled=${!this._twoFactorPassword}
              >
                Submit
              </button>
              <button class="button button-secondary" @click=${this._cancelAuth}>
                Cancel
              </button>
            </div>
          </div>
        `;

      case 'verifying_2fa':
        return html`
          <div class="wizard">
            <div class="loading">
              <div class="spinner"></div>
              <span>Verifying 2FA password...</span>
            </div>
          </div>
        `;

      default:
        return nothing;
    }
  }

  private _renderConnected() {
    const account = this._status?.account;
    return html`
      <div class="account-info">
        ${account?.name ? html`
          <div class="account-row">
            <span class="account-label">Name:</span>
            <span class="account-value">${account.name}</span>
          </div>
        ` : nothing}
        ${account?.username ? html`
          <div class="account-row">
            <span class="account-label">Username:</span>
            <span class="account-value">@${account.username}</span>
          </div>
        ` : nothing}
        ${account?.phone ? html`
          <div class="account-row">
            <span class="account-label">Phone:</span>
            <span class="account-value">${account.phone}</span>
          </div>
        ` : nothing}
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

    if (!this._testResult.connected) {
      return html`
        <div class="message error">
          Connection test failed: ${this._testResult.error || 'Unknown error'}
        </div>
      `;
    }

    return html`
      <div class="test-result">
        <h4>Connection successful!</h4>
        ${this._testResult.dialogs && this._testResult.dialogs.length > 0 ? html`
          <p>Recent chats:</p>
          <ul>
            ${this._testResult.dialogs.map(dialog => html`
              <li>${dialog.name} (${dialog.type})</li>
            `)}
          </ul>
        ` : html`<p>No recent chats found.</p>`}
      </div>
    `;
  }

  render() {
    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Telegram</h3>
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
    'telegram-card': TelegramCard;
  }
}
