/**
 * Frank Bot Dashboard entry point.
 *
 * This is the main entry point for both dev mode and library builds.
 * It exports the dashboard component for embedding.
 */

import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import * as api from './lib/api.js';

// Import styles
import tokensCSS from './styles/tokens.css?inline';

/**
 * Main Frank Bot dashboard component.
 *
 * @element frank-bot-dashboard
 *
 * @attr {string} api-base - Base URL for API requests (default: /api)
 * @attr {string} session-token - Optional session token for auth
 */
@customElement('frank-bot-dashboard')
export class FrankBotDashboard extends LitElement {
  static styles = css`
    ${tokensCSS}

    :host {
      display: block;
      font-family: var(--font-family);
      color: var(--color-text);
    }

    .dashboard {
      display: grid;
      gap: var(--spacing-lg);
    }

    .card {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-md);
      padding: var(--spacing-lg);
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
    }

    .status-badge {
      display: inline-block;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
      font-weight: 500;
    }

    .status-badge.success {
      background: var(--color-success);
      color: white;
    }

    .status-badge.warning {
      background: var(--color-warning);
      color: black;
    }

    .status-badge.error {
      background: var(--color-error);
      color: white;
    }

    .status-badge.neutral {
      background: var(--color-border);
      color: var(--color-text);
    }

    .placeholder {
      color: var(--color-text-muted);
      font-style: italic;
    }

    .button {
      padding: var(--spacing-sm) var(--spacing-md);
      border-radius: var(--border-radius-sm);
      border: none;
      cursor: pointer;
      font-size: var(--font-size-base);
      font-weight: 500;
      transition: background var(--transition-fast);
    }

    .button-primary {
      background: var(--color-primary);
      color: white;
    }

    .button-primary:hover {
      background: color-mix(in srgb, var(--color-primary) 80%, white);
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
    }

    .spinner {
      width: 16px;
      height: 16px;
      border: 2px solid var(--color-border);
      border-top-color: var(--color-primary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `;

  @property({ type: String, attribute: 'api-base' })
  apiBase = '/api';

  @property({ type: String, attribute: 'session-token' })
  sessionToken = '';

  @state() private _initialized = false;

  connectedCallback() {
    super.connectedCallback();
    this._initialize();
  }

  updated(changedProperties: Map<string, unknown>) {
    if (changedProperties.has('apiBase') || changedProperties.has('sessionToken')) {
      api.configure({
        apiBase: this.apiBase,
        sessionToken: this.sessionToken || this._getSessionFromCookie(),
      });
    }
  }

  private _initialize() {
    // Configure API client
    api.configure({
      apiBase: this.apiBase,
      sessionToken: this.sessionToken || this._getSessionFromCookie(),
    });

    this._initialized = true;
  }

  private _getSessionFromCookie(): string | undefined {
    // Try to read stytch_session_token from cookies
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'stytch_session_token') {
        return value;
      }
    }
    return undefined;
  }

  render() {
    if (!this._initialized) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Initializing...</span>
        </div>
      `;
    }

    return html`
      <div class="dashboard">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Telegram</h3>
            <span class="status-badge neutral">Loading...</span>
          </div>
          <p class="placeholder">
            Telegram card component will be implemented in frank_bot-00035.
          </p>
        </div>

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Scripts</h3>
          </div>
          <p class="placeholder">
            Scripts card component will be implemented in frank_bot-00037.
          </p>
        </div>

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Jobs</h3>
          </div>
          <p class="placeholder">
            Jobs card component will be implemented in frank_bot-00038.
          </p>
        </div>
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'frank-bot-dashboard': FrankBotDashboard;
  }
}
