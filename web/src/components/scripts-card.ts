/**
 * Scripts card component for Frank Bot dashboard.
 *
 * Displays list of meta scripts with details.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { Script } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

/**
 * Scripts card component.
 *
 * @element scripts-card
 */
@customElement('scripts-card')
export class ScriptsCard extends LitElement {
  static styles = css`
    ${unsafeCSS(tokensCSS)}

    :host {
      display: block;
      /* Prevent expanding beyond container */
      min-width: 0;
      max-width: 100%;
    }

    .card {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-md);
      padding: var(--spacing-lg);
      /* Kente green left accent - scripts are "growth" */
      border-left: 3px solid var(--kente-green);
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

    .scripts-list {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .script-item {
      background: var(--color-surface-hover);
      border-radius: var(--border-radius-sm);
      overflow: hidden;
      border-left: 2px solid transparent;
      transition: border-color var(--transition-fast);
      /* Prevent expanding beyond container */
      min-width: 0;
    }

    .script-item:hover {
      border-left-color: var(--kente-green);
    }

    .script-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--spacing-md);
      cursor: pointer;
      transition: background var(--transition-fast);
    }

    .script-header:hover {
      background: var(--color-border);
    }

    .script-info {
      flex: 1;
      min-width: 0;
    }

    .script-name {
      font-weight: 600;
      margin-bottom: var(--spacing-xs);
      word-break: break-word;
      color: var(--kente-gold-light);
    }

    .script-description {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .script-meta {
      display: flex;
      gap: var(--spacing-md);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      margin-left: var(--spacing-md);
      white-space: nowrap;
    }

    .expand-icon {
      transition: transform var(--transition-fast);
      color: var(--kente-gold);
    }

    .expand-icon.expanded {
      transform: rotate(180deg);
    }

    .script-details {
      padding: 0 var(--spacing-md) var(--spacing-md);
      border-top: 1px solid var(--color-border);
    }

    .script-details h4 {
      font-size: var(--font-size-sm);
      color: var(--kente-gold);
      margin: var(--spacing-md) 0 var(--spacing-sm);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .script-details p {
      margin: 0;
      line-height: 1.5;
    }

    .parameters-list {
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .parameters-list li {
      padding: var(--spacing-xs) 0;
      border-bottom: 1px solid var(--color-border);
    }

    .parameters-list li:last-child {
      border-bottom: none;
    }

    .param-name {
      font-family: monospace;
      font-weight: 600;
      color: var(--kente-gold);
    }

    .param-type {
      font-family: monospace;
      color: var(--color-text-muted);
    }

    .param-description {
      margin-top: var(--spacing-xs);
      font-size: var(--font-size-sm);
    }

    .code-block {
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-md);
      overflow-x: auto;
      font-family: monospace;
      font-size: var(--font-size-sm);
      white-space: pre;
      /* Prevent code from pushing parent wider */
      max-width: 100%;
      box-sizing: border-box;
    }

    .script-created {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }
  `;

  @state() private _scripts: Script[] = [];
  @state() private _loading = true;
  @state() private _error: string | null = null;
  @state() private _expandedScriptId: string | null = null;
  @state() private _scriptCode: Map<string, string> = new Map();
  @state() private _loadingCode: Set<string> = new Set();

  connectedCallback() {
    super.connectedCallback();
    this._fetchScripts();
  }

  private async _fetchScripts() {
    this._loading = true;
    this._error = null;

    try {
      const response = await api.getScripts();
      this._scripts = response.scripts;
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch scripts';
    } finally {
      this._loading = false;
    }
  }

  private async _toggleExpand(scriptId: string) {
    if (this._expandedScriptId === scriptId) {
      this._expandedScriptId = null;
      return;
    }

    this._expandedScriptId = scriptId;

    // Load script code if not already loaded
    if (!this._scriptCode.has(scriptId) && !this._loadingCode.has(scriptId)) {
      await this._loadScriptCode(scriptId);
    }
  }

  private async _loadScriptCode(scriptId: string) {
    this._loadingCode = new Set([...this._loadingCode, scriptId]);

    try {
      const code = await api.getScriptCode(scriptId);
      this._scriptCode = new Map([...this._scriptCode, [scriptId, code]]);
    } catch (err) {
      console.error('Failed to load script code:', err);
    } finally {
      const newSet = new Set(this._loadingCode);
      newSet.delete(scriptId);
      this._loadingCode = newSet;
    }
  }

  private _formatDate(isoDate: string): string {
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

  private _renderContent() {
    if (this._loading) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading scripts...</span>
        </div>
      `;
    }

    if (this._error) {
      return html`
        <div class="message error">${this._error}</div>
      `;
    }

    if (this._scripts.length === 0) {
      return html`
        <div class="empty-state">
          <p>No scripts found.</p>
          <p>Scripts are created when ChatGPT executes code via the /frank/execute endpoint.</p>
        </div>
      `;
    }

    return html`
      <div class="scripts-list">
        ${this._scripts.map(script => this._renderScript(script))}
      </div>
    `;
  }

  private _renderScript(script: Script) {
    const isExpanded = this._expandedScriptId === script.id;
    const code = this._scriptCode.get(script.id);
    const isLoadingCode = this._loadingCode.has(script.id);

    return html`
      <div class="script-item">
        <div
          class="script-header"
          @click=${() => this._toggleExpand(script.id)}
          role="button"
          tabindex="0"
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              this._toggleExpand(script.id);
            }
          }}
        >
          <div class="script-info">
            <div class="script-name">${script.slug}</div>
            <div class="script-description">${script.description || 'No description'}</div>
          </div>
          <div class="script-meta">
            <span>${this._formatDate(script.created_at)}</span>
            <span class="expand-icon ${isExpanded ? 'expanded' : ''}">▼</span>
          </div>
        </div>

        ${isExpanded ? html`
          <div class="script-details">
            ${script.description ? html`
              <h4>Description</h4>
              <p>${script.description}</p>
            ` : nothing}

            ${script.parameters.length > 0 ? html`
              <h4>Parameters</h4>
              <ul class="parameters-list">
                ${script.parameters.map(param => html`
                  <li>
                    <span class="param-name">${param.name}</span>
                    ${param.type ? html`<span class="param-type">: ${param.type}</span>` : nothing}
                    ${param.description ? html`
                      <div class="param-description">${param.description}</div>
                    ` : nothing}
                  </li>
                `)}
              </ul>
            ` : nothing}

            ${script.example ? html`
              <h4>Example</h4>
              <div class="code-block">${script.example}</div>
            ` : nothing}

            <h4>Source Code</h4>
            ${isLoadingCode ? html`
              <div class="loading">
                <div class="spinner"></div>
                <span>Loading code...</span>
              </div>
            ` : code ? html`
              <div class="code-block">${code}</div>
            ` : html`
              <p>Failed to load source code.</p>
            `}

            <div class="script-created">
              <strong>Script ID:</strong> ${script.id}
            </div>
          </div>
        ` : nothing}
      </div>
    `;
  }

  render() {
    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Scripts</h3>
          <button
            class="button button-secondary button-icon"
            @click=${this._fetchScripts}
            ?disabled=${this._loading}
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
    'scripts-card': ScriptsCard;
  }
}
