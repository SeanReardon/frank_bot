/**
 * SMS messages card component for Frank Bot dashboard.
 *
 * Displays recent SMS messages grouped by conversation,
 * with filtering by contact/phone.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { SmsMessage, SmsMessagesResponse } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

interface Conversation {
  phone: string;
  contact: string | null;
  messages: SmsMessage[];
}

/**
 * SMS messages card component.
 *
 * @element sms-card
 */
@customElement('sms-card')
export class SmsCard extends LitElement {
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
      /* Kente green left accent for messages */
      border-left: 3px solid var(--kente-green);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: var(--spacing-md);
      gap: var(--spacing-md);
      flex-wrap: wrap;
    }

    .card-title {
      font-size: var(--font-size-lg);
      font-weight: 600;
      margin: 0;
      color: var(--kente-gold-light);
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
    }

    .filter-input {
      padding: var(--spacing-xs) var(--spacing-sm);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      background: var(--color-bg);
      color: var(--color-text);
      font-size: var(--font-size-sm);
      width: 160px;
    }

    .filter-input:focus {
      outline: none;
      border-color: var(--kente-gold);
    }

    .filter-input::placeholder {
      color: var(--color-text-muted);
    }

    .card-content {
      color: var(--color-text);
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

    .message.info {
      background: color-mix(in srgb, var(--kente-gold) 15%, transparent);
      border: 1px solid var(--kente-gold-dark);
    }

    .empty-state {
      text-align: center;
      color: var(--color-text-muted);
      padding: var(--spacing-xl);
    }

    .conversations {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-lg);
    }

    .conversation {
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-md);
      overflow: hidden;
    }

    .conversation-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--spacing-sm) var(--spacing-md);
      background: var(--color-surface-hover);
      border-bottom: 1px solid var(--color-border);
    }

    .conversation-contact {
      font-weight: 600;
      color: var(--kente-gold-light);
    }

    .conversation-phone {
      color: var(--color-text-muted);
      font-size: var(--font-size-sm);
      font-family: monospace;
    }

    .conversation-messages {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-xs);
      padding: var(--spacing-sm);
      max-height: 300px;
      overflow-y: auto;
    }

    .sms-message {
      display: flex;
      flex-direction: column;
      max-width: 80%;
      padding: var(--spacing-sm) var(--spacing-md);
      border-radius: var(--border-radius-md);
      font-size: var(--font-size-sm);
    }

    .sms-message.outbound {
      align-self: flex-end;
      background: var(--kente-gold-dark);
      color: white;
      border-bottom-right-radius: var(--border-radius-xs);
    }

    .sms-message.inbound {
      align-self: flex-start;
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-bottom-left-radius: var(--border-radius-xs);
    }

    .sms-message-text {
      white-space: pre-wrap;
      word-break: break-word;
    }

    .sms-message-meta {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      margin-top: var(--spacing-xs);
      font-size: 10px;
      opacity: 0.7;
    }

    .sms-message-time {
      text-align: right;
    }

    .attachment-indicator {
      display: inline-flex;
      align-items: center;
      gap: 2px;
    }

    .count-badge {
      display: inline-block;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
      background: var(--color-border);
      color: var(--color-text);
    }
  `;

  @state() private _response: SmsMessagesResponse | null = null;
  @state() private _loading = true;
  @state() private _error: string | null = null;
  @state() private _filter = '';
  @state() private _filterTimeout: number | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._fetchMessages();
  }

  private async _fetchMessages() {
    this._loading = true;
    this._error = null;

    try {
      const options: api.GetSmsMessagesOptions = { limit: 50 };

      // Apply filter if set
      if (this._filter.trim()) {
        // If filter looks like a phone number, use phone filter
        if (this._filter.match(/^\+?\d[\d\s-]+$/)) {
          options.phone = this._filter.trim();
        } else {
          // Otherwise use contact filter
          options.contact = this._filter.trim();
        }
      }

      this._response = await api.getSmsMessages(options);
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch messages';
    } finally {
      this._loading = false;
    }
  }

  private _handleFilterInput(e: InputEvent) {
    this._filter = (e.target as HTMLInputElement).value;

    // Debounce the filter
    if (this._filterTimeout !== null) {
      clearTimeout(this._filterTimeout);
    }

    this._filterTimeout = window.setTimeout(() => {
      this._fetchMessages();
      this._filterTimeout = null;
    }, 300);
  }

  private _handleRefresh() {
    this._fetchMessages();
  }

  private _groupByConversation(messages: SmsMessage[]): Conversation[] {
    const grouped = new Map<string, Conversation>();

    for (const msg of messages) {
      if (!grouped.has(msg.phone)) {
        grouped.set(msg.phone, {
          phone: msg.phone,
          contact: msg.contact,
          messages: [],
        });
      }
      grouped.get(msg.phone)!.messages.push(msg);
    }

    // Sort conversations by most recent message
    const conversations = Array.from(grouped.values());
    conversations.sort((a, b) => {
      const aTime = new Date(a.messages[0]?.timestamp || 0).getTime();
      const bTime = new Date(b.messages[0]?.timestamp || 0).getTime();
      return bTime - aTime;
    });

    return conversations;
  }

  private _formatTime(isoDate: string): string {
    try {
      const date = new Date(isoDate);
      const now = new Date();
      const isToday = date.toDateString() === now.toDateString();

      if (isToday) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      return date.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
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
          <span>Loading SMS messages...</span>
        </div>
      `;
    }

    if (this._error) {
      return html`
        <div class="message error">${this._error}</div>
      `;
    }

    if (!this._response || this._response.count === 0) {
      return html`
        <div class="empty-state">
          <p>No SMS messages found.</p>
          ${this._filter ? html`<p>Try clearing the filter.</p>` : nothing}
        </div>
      `;
    }

    const conversations = this._groupByConversation(this._response.messages);

    return html`
      <div class="conversations">
        ${conversations.map(conv => this._renderConversation(conv))}
      </div>
    `;
  }

  private _renderConversation(conv: Conversation) {
    const displayName = conv.contact || conv.phone;

    return html`
      <div class="conversation">
        <div class="conversation-header">
          <div>
            <span class="conversation-contact">${displayName}</span>
            ${conv.contact ? html`
              <span class="conversation-phone"> (${conv.phone})</span>
            ` : nothing}
          </div>
          <span class="count-badge">${conv.messages.length} messages</span>
        </div>
        <div class="conversation-messages">
          ${conv.messages.map(msg => this._renderMessage(msg))}
        </div>
      </div>
    `;
  }

  private _renderMessage(msg: SmsMessage) {
    return html`
      <div class="sms-message ${msg.direction}">
        <span class="sms-message-text">${msg.preview}</span>
        <div class="sms-message-meta">
          ${msg.hasAttachments ? html`
            <span class="attachment-indicator" title="Has attachments">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z"/>
              </svg>
            </span>
          ` : nothing}
          <span class="sms-message-time">${this._formatTime(msg.timestamp)}</span>
        </div>
      </div>
    `;
  }

  render() {
    const messageCount = this._response?.count || 0;

    return html`
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">SMS Messages</h3>
          <div class="header-actions">
            <input
              type="text"
              class="filter-input"
              placeholder="Filter by contact/phone..."
              .value=${this._filter}
              @input=${this._handleFilterInput}
            />
            <button
              class="button button-secondary"
              @click=${this._handleRefresh}
              ?disabled=${this._loading}
              title="Refresh messages"
            >
              ${this._loading ? '...' : 'Refresh'}
            </button>
          </div>
        </div>
        <div class="card-content">
          ${!this._loading && this._response ? html`
            <div class="message info" style="margin-bottom: var(--spacing-md); margin-top: 0;">
              Showing ${messageCount} message${messageCount !== 1 ? 's' : ''}
            </div>
          ` : nothing}
          ${this._renderContent()}
        </div>
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'sms-card': SmsCard;
  }
}
