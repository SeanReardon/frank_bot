/**
 * Frank Bot Dashboard entry point.
 *
 * This is the main entry point for both dev mode and library builds.
 * It exports the dashboard component for embedding.
 */

import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import * as api from './lib/api.js';

// Import components
import './components/telegram-card.js';
import './components/scripts-card.js';
import './components/jobs-card.js';

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

    /* Kente-inspired decorative stripe at top of dashboard */
    .dashboard::before {
      content: '';
      display: block;
      height: 4px;
      background: var(--kente-stripe);
      border-radius: var(--border-radius-sm);
      margin-bottom: var(--spacing-sm);
    }

    .card {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-md);
      padding: var(--spacing-lg);
      /* Subtle gold left accent border */
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
      font-weight: 600;
      transition: all var(--transition-fast);
    }

    .button-primary {
      background: var(--kente-gold);
      color: var(--kente-black);
    }

    .button-primary:hover {
      background: var(--kente-gold-light);
      box-shadow: 0 2px 8px rgba(218, 165, 32, 0.3);
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
      border-top-color: var(--kente-gold);
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
        <telegram-card></telegram-card>

        <scripts-card></scripts-card>

        <jobs-card></jobs-card>
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
