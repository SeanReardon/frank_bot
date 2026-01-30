/**
 * Frank Bot Dashboard entry point.
 *
 * This is the main entry point for both dev mode and library builds.
 * It exports the dashboard component for embedding.
 */

import { LitElement, html, css, unsafeCSS } from 'lit';
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
    ${unsafeCSS(tokensCSS)}

    :host {
      display: flex;
      flex-direction: column;
      width: 100%;
      /* Use 100% height from parent, not viewport - parent handles scroll area */
      height: 100%;
      font-family: var(--font-family);
      color: var(--color-text);
      background: var(--color-background);
      /* Always show scrollbar to prevent layout shift when content changes */
      overflow-y: scroll;
      overflow-x: hidden;
      /* Ensure scrolling works with keyboard navigation */
      scroll-behavior: smooth;
      /* Support for keyboard scrolling */
      outline: none;
      -webkit-overflow-scrolling: touch;
    }

    :host(:focus) {
      outline: none;
    }

    .dashboard {
      display: grid;
      gap: var(--spacing-lg);
      /* Match claudia exactly: 2rem padding, 1200px max-width */
      padding: 2rem;
      max-width: 1200px;
      margin: 0 auto;
      box-sizing: border-box;
      flex: 1;
      /* Prevent children from expanding beyond max-width */
      min-width: 0;
    }

    .version-footer {
      padding: var(--spacing-md) var(--spacing-lg);
      border-top: 1px solid var(--color-border);
      background: var(--color-surface);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-md);
      justify-content: center;
    }

    .version-item {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
    }

    .version-label {
      font-weight: 500;
    }

    .version-link {
      color: var(--kente-gold);
      text-decoration: none;
      font-family: monospace;
    }

    .version-link:hover {
      color: var(--kente-gold-light);
      text-decoration: underline;
    }

    .version-text {
      font-family: monospace;
      color: var(--color-text-muted);
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
  @state() private _apiCommit: string | null = null;
  @state() private _webCommit: string = api.getWebCommit();

  connectedCallback() {
    super.connectedCallback();
    this._initialize();
    this._fetchVersion();
    // Make element focusable and add keyboard handler
    this.setAttribute('tabindex', '0');
    this.addEventListener('keydown', this._handleKeydown);
  }

  private async _fetchVersion() {
    try {
      const version = await api.getVersion();
      this._apiCommit = version.api.commit;
    } catch (err) {
      console.warn('Failed to fetch API version:', err);
      this._apiCommit = null;
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.removeEventListener('keydown', this._handleKeydown);
  }

  private _handleKeydown = (e: KeyboardEvent) => {
    // Handle keyboard scrolling
    const scrollAmount = 100; // pixels to scroll per arrow key
    const pageScrollAmount = this.clientHeight * 0.9; // 90% of visible height

    switch (e.key) {
      case 'ArrowDown':
        this.scrollBy({ top: scrollAmount, behavior: 'smooth' });
        e.preventDefault();
        break;
      case 'ArrowUp':
        this.scrollBy({ top: -scrollAmount, behavior: 'smooth' });
        e.preventDefault();
        break;
      case 'PageDown':
      case ' ': // Space
        if (!e.shiftKey) {
          this.scrollBy({ top: pageScrollAmount, behavior: 'smooth' });
          e.preventDefault();
        }
        break;
      case 'PageUp':
        this.scrollBy({ top: -pageScrollAmount, behavior: 'smooth' });
        e.preventDefault();
        break;
      case 'Home':
        this.scrollTo({ top: 0, behavior: 'smooth' });
        e.preventDefault();
        break;
      case 'End':
        this.scrollTo({ top: this.scrollHeight, behavior: 'smooth' });
        e.preventDefault();
        break;
    }

    // Handle Shift+Space for page up
    if (e.key === ' ' && e.shiftKey) {
      this.scrollBy({ top: -pageScrollAmount, behavior: 'smooth' });
      e.preventDefault();
    }
  };

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

  private _renderVersionItem(label: string, commit: string | null, repo: string) {
    if (!commit || commit === 'dev' || commit === 'unknown') {
      return html`
        <div class="version-item">
          <span class="version-label">${label}:</span>
          <span class="version-text">dev</span>
        </div>
      `;
    }
    
    const shortCommit = commit.substring(0, 7);
    const commitUrl = `https://github.com/SeanReardon/${repo}/commit/${commit}`;
    
    return html`
      <div class="version-item">
        <span class="version-label">${label}:</span>
        <a href="${commitUrl}" target="_blank" rel="noopener noreferrer" class="version-link">${shortCommit}</a>
      </div>
    `;
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
      
      <div class="version-footer">
        ${this._renderVersionItem('frank_bot-web', this._webCommit, 'frank_bot')}
        ${this._renderVersionItem('frank_bot', this._apiCommit, 'frank_bot')}
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
