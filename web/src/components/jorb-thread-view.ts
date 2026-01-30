/**
 * Jorb message thread view component.
 *
 * Displays full conversation history for a jorb with message details,
 * channel indicators, and agent reasoning.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { Jorb, JorbMessage, JorbStatus } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

/**
 * Jorb thread view component.
 *
 * @element jorb-thread-view
 * @attr {string} jorb-id - The ID of the jorb to display
 * @fires close - Fired when the user wants to close the thread view
 */
@customElement('jorb-thread-view')
export class JorbThreadView extends LitElement {
  static styles = css`
    ${unsafeCSS(tokensCSS)}

    :host {
      display: block;
    }

    .thread-container {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-md);
      /* Gold accent for jorb context */
      border-left: 3px solid var(--kente-gold);
      display: flex;
      flex-direction: column;
      max-height: 80vh;
    }

    .thread-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--spacing-md) var(--spacing-lg);
      border-bottom: 1px solid var(--color-border);
      background: var(--color-surface-hover);
      gap: var(--spacing-md);
      flex-wrap: wrap;
    }

    .thread-title {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-xs);
    }

    .thread-title h3 {
      margin: 0;
      font-size: var(--font-size-lg);
      font-weight: 600;
      color: var(--kente-gold-light);
    }

    .thread-subtitle {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
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

    .auto-scroll {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }

    .auto-scroll input {
      cursor: pointer;
      accent-color: var(--kente-gold);
    }

    .status-badge {
      display: inline-block;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
      font-weight: 500;
      white-space: nowrap;
    }

    .messages-container {
      flex: 1;
      overflow-y: auto;
      padding: var(--spacing-md) var(--spacing-lg);
      display: flex;
      flex-direction: column;
      gap: var(--spacing-md);
      min-height: 300px;
      scroll-behavior: smooth;
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

    .empty-state {
      text-align: center;
      color: var(--color-text-muted);
      padding: var(--spacing-xl);
    }

    .load-more {
      display: flex;
      justify-content: center;
      padding: var(--spacing-md);
    }

    .message {
      display: flex;
      flex-direction: column;
      max-width: 85%;
    }

    .message.inbound {
      align-self: flex-start;
    }

    .message.outbound {
      align-self: flex-end;
    }

    .message-bubble {
      padding: var(--spacing-md);
      border-radius: var(--border-radius-md);
      position: relative;
    }

    .message.inbound .message-bubble {
      background: var(--color-surface-hover);
      border-left: 3px solid var(--kente-blue);
      border-top-left-radius: 0;
    }

    .message.outbound .message-bubble {
      background: color-mix(in srgb, var(--kente-green) 20%, var(--color-surface));
      border-right: 3px solid var(--kente-green);
      border-top-right-radius: 0;
    }

    .message-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--spacing-md);
      margin-bottom: var(--spacing-sm);
      font-size: var(--font-size-sm);
    }

    .message-sender {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
      font-weight: 500;
    }

    .channel-icon {
      font-size: var(--font-size-base);
    }

    .message-time {
      color: var(--color-text-muted);
      font-size: var(--font-size-xs);
    }

    .message-content {
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.5;
    }

    .message-reasoning {
      margin-top: var(--spacing-sm);
      border-top: 1px dashed var(--color-border);
      padding-top: var(--spacing-sm);
    }

    .reasoning-toggle {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
      color: var(--kente-gold);
      font-size: var(--font-size-sm);
      cursor: pointer;
      background: none;
      border: none;
      padding: 0;
      font-weight: 500;
    }

    .reasoning-toggle:hover {
      color: var(--kente-gold-light);
    }

    .reasoning-content {
      margin-top: var(--spacing-sm);
      padding: var(--spacing-sm);
      background: var(--color-bg);
      border-radius: var(--border-radius-sm);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
      white-space: pre-wrap;
      word-break: break-word;
    }

    .thread-footer {
      padding: var(--spacing-md) var(--spacing-lg);
      border-top: 1px solid var(--color-border);
      background: var(--color-surface-hover);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }
  `;

  @property({ type: String, attribute: 'jorb-id' })
  jorbId = '';

  @state() private _jorb: Jorb | null = null;
  @state() private _messages: JorbMessage[] = [];
  @state() private _loading = true;
  @state() private _loadingMore = false;
  @state() private _error: string | null = null;
  @state() private _hasMore = false;
  @state() private _autoScroll = true;
  @state() private _expandedReasoning: Set<string> = new Set();

  private _offset = 0;
  private _limit = 50;
  private _messagesContainer: HTMLElement | null = null;

  connectedCallback() {
    super.connectedCallback();
    if (this.jorbId) {
      this._fetchJorb();
    }
  }

  updated(changedProperties: Map<string, unknown>) {
    super.updated(changedProperties);

    if (changedProperties.has('jorbId') && this.jorbId) {
      this._offset = 0;
      this._messages = [];
      this._fetchJorb();
    }

    // Auto-scroll to bottom when messages change
    if (changedProperties.has('_messages') && this._autoScroll) {
      this._scrollToBottom();
    }
  }

  private async _fetchJorb() {
    this._loading = true;
    this._error = null;

    try {
      // Fetch jorb with initial messages
      const jorb = await api.getJorb(this.jorbId, true, this._limit);
      this._jorb = jorb;
      this._messages = jorb.messages || [];
      this._hasMore = this._messages.length >= this._limit;
      this._offset = this._messages.length;
    } catch (err) {
      this._error = err instanceof Error ? err.message : 'Failed to fetch jorb';
    } finally {
      this._loading = false;
    }
  }

  private async _loadMore() {
    if (this._loadingMore || !this._hasMore) return;

    this._loadingMore = true;

    try {
      const response = await api.getJorbMessages(this.jorbId, {
        limit: this._limit,
        offset: this._offset,
      });

      // Prepend older messages
      this._messages = [...response.messages, ...this._messages];
      this._offset += response.messages.length;
      this._hasMore = response.messages.length >= this._limit;
    } catch (err) {
      console.error('Failed to load more messages:', err);
    } finally {
      this._loadingMore = false;
    }
  }

  private async _refresh() {
    this._offset = 0;
    this._messages = [];
    await this._fetchJorb();
  }

  private _scrollToBottom() {
    requestAnimationFrame(() => {
      if (!this._messagesContainer) {
        this._messagesContainer = this.renderRoot.querySelector('.messages-container');
      }
      if (this._messagesContainer) {
        this._messagesContainer.scrollTop = this._messagesContainer.scrollHeight;
      }
    });
  }

  private _handleAutoScrollChange(e: Event) {
    const checkbox = e.target as HTMLInputElement;
    this._autoScroll = checkbox.checked;
    if (this._autoScroll) {
      this._scrollToBottom();
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

  private _toggleReasoning(messageId: string) {
    const newSet = new Set(this._expandedReasoning);
    if (newSet.has(messageId)) {
      newSet.delete(messageId);
    } else {
      newSet.add(messageId);
    }
    this._expandedReasoning = newSet;
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
    const colors: Record<JorbStatus, { bg: string; text: string }> = {
      planning: { bg: 'var(--color-border)', text: 'var(--color-text)' },
      running: { bg: 'var(--kente-blue)', text: 'white' },
      paused: { bg: 'var(--kente-orange)', text: 'white' },
      complete: { bg: 'var(--kente-green)', text: 'white' },
      failed: { bg: 'var(--kente-red)', text: 'white' },
      cancelled: { bg: 'var(--color-border)', text: 'var(--color-text)' },
    };
    const c = colors[status] || colors.planning;
    return `background: ${c.bg}; color: ${c.text};`;
  }

  private _formatTime(isoDate: string): string {
    try {
      const date = new Date(isoDate);
      return date.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoDate;
    }
  }

  private _formatDate(isoDate: string): string {
    try {
      const date = new Date(isoDate);
      return date.toLocaleDateString(undefined, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
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

  private _groupMessagesByDate(messages: JorbMessage[]): Map<string, JorbMessage[]> {
    const groups = new Map<string, JorbMessage[]>();

    for (const msg of messages) {
      const dateKey = this._formatDate(msg.timestamp);
      const existing = groups.get(dateKey) || [];
      groups.set(dateKey, [...existing, msg]);
    }

    return groups;
  }

  private _renderMessage(msg: JorbMessage) {
    const isExpanded = this._expandedReasoning.has(msg.id);
    const senderName = msg.direction === 'inbound'
      ? (msg.sender_name || msg.sender || 'Unknown')
      : 'Frank Bot';

    return html`
      <div class="message ${msg.direction}">
        <div class="message-bubble">
          <div class="message-header">
            <span class="message-sender">
              <span class="channel-icon">${this._getChannelIcon(msg.channel)}</span>
              ${senderName}
            </span>
            <span class="message-time" title="${msg.timestamp}">
              ${this._formatTime(msg.timestamp)}
            </span>
          </div>
          <div class="message-content">${msg.content}</div>
          ${msg.direction === 'outbound' && msg.agent_reasoning ? html`
            <div class="message-reasoning">
              <button
                class="reasoning-toggle"
                @click=${() => this._toggleReasoning(msg.id)}
              >
                ${isExpanded ? '▼' : '▶'} Agent Reasoning
              </button>
              ${isExpanded ? html`
                <div class="reasoning-content">${msg.agent_reasoning}</div>
              ` : nothing}
            </div>
          ` : nothing}
        </div>
      </div>
    `;
  }

  private _renderDateSeparator(date: string) {
    return html`
      <div style="
        display: flex;
        align-items: center;
        gap: var(--spacing-md);
        color: var(--color-text-muted);
        font-size: var(--font-size-sm);
        margin: var(--spacing-md) 0;
      ">
        <div style="flex: 1; height: 1px; background: var(--color-border);"></div>
        <span>${date}</span>
        <div style="flex: 1; height: 1px; background: var(--color-border);"></div>
      </div>
    `;
  }

  private _renderMessages() {
    if (this._loading) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading messages...</span>
        </div>
      `;
    }

    if (this._error) {
      return html`<div class="error">${this._error}</div>`;
    }

    if (this._messages.length === 0) {
      return html`
        <div class="empty-state">
          <p>No messages in this thread yet.</p>
        </div>
      `;
    }

    const grouped = this._groupMessagesByDate(this._messages);

    return html`
      ${this._hasMore ? html`
        <div class="load-more">
          <button
            class="button button-secondary"
            @click=${this._loadMore}
            ?disabled=${this._loadingMore}
          >
            ${this._loadingMore ? 'Loading...' : 'Load Older Messages'}
          </button>
        </div>
      ` : nothing}

      ${Array.from(grouped.entries()).map(([date, msgs]) => html`
        ${this._renderDateSeparator(date)}
        ${msgs.map(msg => this._renderMessage(msg))}
      `)}
    `;
  }

  render() {
    const jorb = this._jorb;

    return html`
      <div class="thread-container">
        <div class="thread-header">
          <div class="thread-title">
            <h3>${jorb?.name || 'Loading...'}</h3>
            <div class="thread-subtitle">
              ${jorb ? html`
                <span class="status-badge" style=${this._getStatusStyle(jorb.status)}>${jorb.status}</span>
                <span style="margin-left: var(--spacing-sm);">Updated ${this._formatRelativeTime(jorb.updated_at)}</span>
              ` : nothing}
            </div>
          </div>
          <div class="header-controls">
            <label class="auto-scroll">
              <input
                type="checkbox"
                ?checked=${this._autoScroll}
                @change=${this._handleAutoScrollChange}
              />
              Auto-scroll
            </label>
            <button
              class="button button-secondary button-icon"
              @click=${this._refresh}
              ?disabled=${this._loading}
              title="Refresh"
            >
              ↻
            </button>
            <button
              class="button button-secondary button-icon"
              @click=${this._handleClose}
              title="Close"
            >
              ✕
            </button>
          </div>
        </div>

        <div class="messages-container">
          ${this._renderMessages()}
        </div>

        <div class="thread-footer">
          <span>${this._messages.length} message${this._messages.length !== 1 ? 's' : ''}</span>
          <span>Jorb ID: ${this.jorbId}</span>
        </div>
      </div>
    `;
  }
}

// Type declaration for custom element
declare global {
  interface HTMLElementTagNameMap {
    'jorb-thread-view': JorbThreadView;
  }
}
