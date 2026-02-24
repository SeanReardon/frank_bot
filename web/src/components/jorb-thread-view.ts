/**
 * Jorb message thread view component.
 *
 * Displays full conversation history for a jorb with message details,
 * channel indicators, and agent reasoning.
 */

import { LitElement, html, css, unsafeCSS, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import * as api from '../lib/api.js';
import type { Jorb, JorbMessage, JorbScriptResult, JorbStatus } from '../lib/api.js';

// Import tokens CSS
import tokensCSS from '../styles/tokens.css?inline';

type TimelineItemKind =
  | 'switchboard'
  | 'human'
  | 'message'
  | 'llm'
  | 'script'
  | 'android-image'
  | 'checkpoint'
  | 'outcome';

interface TimelineItem {
  id: string;
  timestamp: string;
  kind: TimelineItemKind;
  title: string;
  summary?: string;
  content?: string;
  details?: unknown;
  imageBase64?: string;
  screenshotPaths?: string[];
  androidTaskId?: string;
  success?: boolean;
}

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
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: var(--spacing-md);
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }

    .footer-left {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-md);
    }

    .footer-metrics {
      display: flex;
      gap: var(--spacing-md);
      padding-left: var(--spacing-md);
      border-left: 1px solid var(--color-border);
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

    .outcome-banner {
      padding: var(--spacing-sm) var(--spacing-md);
      border-radius: var(--border-radius-sm);
      margin-bottom: var(--spacing-md);
    }

    .outcome-banner.complete {
      background: color-mix(in srgb, var(--kente-green) 20%, transparent);
      border: 1px solid var(--kente-green);
      color: var(--kente-green);
    }

    .outcome-banner.failed {
      background: color-mix(in srgb, var(--kente-red) 20%, transparent);
      border: 1px solid var(--kente-red);
      color: var(--kente-red);
    }

    .outcome-banner-header {
      font-weight: 600;
      margin-bottom: var(--spacing-xs);
    }

    .outcome-banner-content {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }

    .legend {
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      background: var(--color-surface-hover);
      padding: var(--spacing-sm) var(--spacing-md);
      margin-bottom: var(--spacing-md);
      display: flex;
      gap: var(--spacing-sm);
      flex-wrap: wrap;
      font-size: var(--font-size-sm);
    }

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: var(--spacing-xs);
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--color-border);
    }

    .timeline {
      display: flex;
      flex-direction: column;
      gap: var(--spacing-sm);
    }

    .timeline-item {
      border: 1px solid var(--color-border);
      border-radius: var(--border-radius-sm);
      padding: var(--spacing-sm) var(--spacing-md);
      background: var(--color-surface-hover);
    }

    .timeline-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--spacing-md);
      margin-bottom: var(--spacing-xs);
      font-size: var(--font-size-sm);
    }

    .timeline-title {
      display: inline-flex;
      align-items: center;
      gap: var(--spacing-xs);
      font-weight: 600;
      color: var(--color-text);
    }

    .timeline-kind {
      font-size: var(--font-size-xs);
      color: var(--color-text-muted);
      border: 1px solid var(--color-border);
      border-radius: 999px;
      padding: 1px 8px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .timeline-content {
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
      font-size: var(--font-size-sm);
    }

    .timeline-summary {
      margin-bottom: var(--spacing-xs);
      color: var(--color-text-muted);
      font-size: var(--font-size-sm);
    }

    .timeline-code {
      margin-top: var(--spacing-xs);
      padding: var(--spacing-sm);
      border-radius: var(--border-radius-sm);
      background: var(--color-bg);
      border: 1px dashed var(--color-border);
      font-family: var(--font-family-mono, monospace);
      font-size: var(--font-size-xs);
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 260px;
      overflow: auto;
    }

    .timeline-image {
      margin-top: var(--spacing-sm);
      max-width: 100%;
      border-radius: var(--border-radius-sm);
      border: 1px solid var(--color-border);
      display: block;
    }

    .screenshot-links {
      margin-top: var(--spacing-sm);
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-xs);
    }

    .screenshot-link {
      padding: 3px 8px;
      border-radius: var(--border-radius-sm);
      border: 1px solid var(--color-border);
      background: var(--color-surface);
      color: var(--kente-blue);
      cursor: pointer;
      font-size: var(--font-size-xs);
    }

    .screenshot-link:hover:not(:disabled) {
      border-color: var(--kente-blue);
    }

    .timeline-item.switchboard { border-left: 3px solid var(--kente-blue); }
    .timeline-item.human { border-left: 3px solid var(--kente-orange); }
    .timeline-item.llm { border-left: 3px solid var(--kente-gold); }
    .timeline-item.script { border-left: 3px solid var(--kente-green); }
    .timeline-item.android-image { border-left: 3px solid var(--kente-blue); }
    .timeline-item.checkpoint { border-left: 3px solid var(--color-border); }
    .timeline-item.outcome { border-left: 3px solid var(--kente-green); }
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
  @state() private _selectedScreenshotPath: string | null = null;
  @state() private _screenshotCache: Map<string, string> = new Map();
  @state() private _loadingScreenshots: Set<string> = new Set();

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
      this._selectedScreenshotPath = null;
      this._screenshotCache = new Map();
      this._loadingScreenshots = new Set();
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

  private _getChannelIcon(channel: string): string {
    switch (channel) {
      case 'telegram':
        return '✈️';
      case 'telegram_bot':
        return '🤖';
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

  private _isLikelyBase64Image(value: unknown): value is string {
    if (typeof value !== 'string') return false;
    const trimmed = value.trim();
    if (trimmed.length < 64) return false;
    return /^[A-Za-z0-9+/=\s]+$/.test(trimmed);
  }

  private _extractImageBase64(result: unknown): string | null {
    if (!result || typeof result !== 'object') return null;
    const obj = result as Record<string, unknown>;
    const candidates = [
      obj.screenshot_base64,
      obj.final_screenshot_base64,
      (obj.result && typeof obj.result === 'object' ? (obj.result as Record<string, unknown>).screenshot_base64 : null),
      (obj.result && typeof obj.result === 'object' ? (obj.result as Record<string, unknown>).final_screenshot_base64 : null),
    ];

    for (const candidate of candidates) {
      if (this._isLikelyBase64Image(candidate)) {
        return candidate.replace(/\s+/g, '');
      }
    }
    return null;
  }

  private _extractScreenshotPaths(result: unknown): string[] {
    if (!result || typeof result !== 'object') return [];
    const obj = result as Record<string, unknown>;
    const collected: string[] = [];

    const addPath = (val: unknown) => {
      if (typeof val === 'string' && val.trim().length > 0) {
        collected.push(val);
      }
    };

    addPath(obj.final_screenshot_path);
    if (Array.isArray(obj.step_screenshot_paths)) {
      obj.step_screenshot_paths.forEach(addPath);
    }

    const nested = obj.result;
    if (nested && typeof nested === 'object') {
      const n = nested as Record<string, unknown>;
      addPath(n.final_screenshot_path);
      if (Array.isArray(n.step_screenshot_paths)) {
        n.step_screenshot_paths.forEach(addPath);
      }
    }

    return Array.from(new Set(collected));
  }

  private _extractAndroidTaskId(result: unknown): string | null {
    if (!result || typeof result !== 'object') return null;
    const obj = result as Record<string, unknown>;
    const id = obj.id || obj.task_id;
    if (typeof id === 'string' && id.trim().length > 0) return id;
    return null;
  }

  private _isTerminalAndroidTaskGet(scriptResult: JorbScriptResult): boolean {
    if (scriptResult.script !== 'android.task_get') return false;
    const result = scriptResult.result;
    if (!result || typeof result !== 'object') return false;
    const status = String((result as Record<string, unknown>).status || '').toLowerCase();
    return ['completed', 'failed', 'cancelled', 'error', 'not_found'].includes(status);
  }

  private _dedupeTerminalTaskResults(scriptResults: JorbScriptResult[]): JorbScriptResult[] {
    const seen = new Set<string>();
    const dedupedReversed: JorbScriptResult[] = [];

    for (let i = scriptResults.length - 1; i >= 0; i--) {
      const current = scriptResults[i];
      if (!this._isTerminalAndroidTaskGet(current)) {
        dedupedReversed.push(current);
        continue;
      }

      const result = current.result as Record<string, unknown> | null;
      const status = String((result?.status as string) || '').toLowerCase();
      const taskId = this._extractAndroidTaskId(current.result) || 'unknown_task';
      const key = `${taskId}:${status}`;
      if (seen.has(key)) continue;
      seen.add(key);
      dedupedReversed.push(current);
    }

    return dedupedReversed.reverse();
  }

  private async _handleScreenshotSelect(path: string) {
    this._selectedScreenshotPath = path;
    if (this._screenshotCache.has(path) || this._loadingScreenshots.has(path)) return;

    const loading = new Set(this._loadingScreenshots);
    loading.add(path);
    this._loadingScreenshots = loading;

    try {
      const response = await api.getAndroidScreenshot(path);
      const next = new Map(this._screenshotCache);
      next.set(path, response.base64);
      this._screenshotCache = next;
    } catch (err) {
      console.error('Failed to load screenshot:', err);
    } finally {
      const done = new Set(this._loadingScreenshots);
      done.delete(path);
      this._loadingScreenshots = done;
    }
  }

  private _safeJson(value: unknown, maxLen = 2200): string {
    try {
      const text = JSON.stringify(value, null, 2);
      return text.length > maxLen ? `${text.slice(0, maxLen)}\n...` : text;
    } catch {
      return String(value);
    }
  }

  private _getScriptTimestamp(scriptResult: JorbScriptResult, index: number): string {
    const ts = scriptResult.timestamp || '';
    if (ts) return ts;
    const fallback = new Date(Date.now() + index).toISOString();
    return fallback;
  }

  private _buildTimelineItems(): TimelineItem[] {
    const items: TimelineItem[] = [];
    const jorb = this._jorb;

    for (const msg of this._messages) {
      const isSeanDirect = msg.sender === 'sean_direct';
      const senderName = isSeanDirect
        ? 'Sean (human)'
        : (msg.direction === 'inbound'
          ? (msg.sender_name || msg.sender || 'Unknown sender')
          : 'Frank Bot');

      if (msg.direction === 'inbound') {
        items.push({
          id: `sw-${msg.id}`,
          timestamp: msg.timestamp,
          kind: 'switchboard',
          title: 'Switchboard Router',
          summary: `Routed inbound ${msg.channel} message to this jorb`,
          content: `${senderName}: ${msg.content}`,
        });
      }

      items.push({
        id: `msg-${msg.id}`,
        timestamp: msg.timestamp,
        kind: isSeanDirect ? 'human' : 'message',
        title: isSeanDirect ? 'Human Talking' : `${msg.direction === 'inbound' ? 'Inbound' : 'Outbound'} Message`,
        summary: `${this._getChannelIcon(msg.channel)} ${senderName}`,
        content: msg.content,
      });

      if (msg.direction === 'outbound' && msg.agent_reasoning) {
        items.push({
          id: `llm-${msg.id}`,
          timestamp: msg.timestamp,
          kind: 'llm',
          title: 'Jorb LLM Reasoning',
          content: msg.agent_reasoning,
        });
      }
    }

    const scriptResults = this._dedupeTerminalTaskResults(jorb?.script_results || []);
    scriptResults.forEach((scriptResult, idx) => {
      const ts = this._getScriptTimestamp(scriptResult, idx);
      const imageBase64 = this._extractImageBase64(scriptResult.result);
      const screenshotPaths = this._extractScreenshotPaths(scriptResult.result);
      const androidTaskId = this._extractAndroidTaskId(scriptResult.result) || undefined;
      const success = Boolean(scriptResult.success);
      items.push({
        id: `script-${idx}-${ts}`,
        timestamp: ts,
        kind: 'script',
        title: `Script: ${scriptResult.script || 'unknown'}`,
        summary: success ? 'Success' : 'Failure',
        details: scriptResult.result,
        content: scriptResult.error || undefined,
        screenshotPaths,
        androidTaskId,
        success,
      });

      if (imageBase64) {
        items.push({
          id: `img-${idx}-${ts}`,
          timestamp: ts,
          kind: 'android-image',
          title: 'Android Phone Picture',
          summary: 'Captured screenshot',
          imageBase64,
        });
      }
    });

    const checkpoints = (jorb as api.JorbDetailResponse | null)?.checkpoints || [];
    checkpoints.forEach((checkpoint) => {
      items.push({
        id: `ckpt-${checkpoint.id}`,
        timestamp: checkpoint.timestamp,
        kind: 'checkpoint',
        title: 'Checkpoint',
        summary: checkpoint.summary,
        content: checkpoint.token_count != null ? `Token count: ${checkpoint.token_count}` : undefined,
      });
    });

    if (jorb?.outcome) {
      items.push({
        id: 'outcome',
        timestamp: jorb.outcome.completed_at || jorb.updated_at,
        kind: 'outcome',
        title: jorb.status === 'complete' ? 'Final Result' : 'Final Failure',
        content: jorb.outcome.result || jorb.outcome.failure_reason || 'No outcome details provided.',
      });
    }

    return items.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  }

  private _renderLegend() {
    return html`
      <div class="legend">
        <span class="legend-item">🧭 Router / Switchboard</span>
        <span class="legend-item">🧠 Jorb LLM</span>
        <span class="legend-item">📱 AndroidPhone Picture</span>
        <span class="legend-item">🗣️ Human Talking</span>
        <span class="legend-item">🧪 Script + Result</span>
        <span class="legend-item">📨 Message</span>
      </div>
    `;
  }

  private _renderTimelineItems() {
    if (this._loading) {
      return html`
        <div class="loading">
          <div class="spinner"></div>
          <span>Loading timeline...</span>
        </div>
      `;
    }

    if (this._error) {
      return html`<div class="error">${this._error}</div>`;
    }

    const timeline = this._buildTimelineItems();

    if (timeline.length === 0) {
      return html`
        <div class="empty-state">
          <p>No timeline entries yet.</p>
        </div>
      `;
    }

    return html`
      ${this._hasMore ? html`
        <div class="load-more">
          <button
            class="button button-secondary"
            @click=${this._loadMore}
            ?disabled=${this._loadingMore}
          >
            ${this._loadingMore ? 'Loading...' : 'Load Older Entries'}
          </button>
        </div>
      ` : nothing}
      ${this._renderLegend()}
      <div class="timeline">
        ${timeline.map((item) => html`
          <div class="timeline-item ${item.kind}">
            <div class="timeline-header">
              <span class="timeline-title">${item.title}</span>
              <span class="message-time" title=${item.timestamp}>
                ${this._formatDate(item.timestamp)} ${this._formatTime(item.timestamp)}
              </span>
            </div>
            <div class="timeline-kind">${item.kind}</div>
            ${item.summary ? html`<div class="timeline-summary">${item.summary}</div>` : nothing}
            ${item.content ? html`<div class="timeline-content">${item.content}</div>` : nothing}
            ${item.details ? html`<pre class="timeline-code">${this._safeJson(item.details)}</pre>` : nothing}
            ${item.screenshotPaths && item.screenshotPaths.length > 0 ? html`
              <div class="timeline-summary">
                ${item.screenshotPaths.length} screenshot${item.screenshotPaths.length !== 1 ? 's' : ''}
                ${item.androidTaskId ? html`(task ${item.androidTaskId})` : nothing}
              </div>
              <div class="screenshot-links">
                ${item.screenshotPaths.map((path, i) => html`
                  <button
                    class="screenshot-link"
                    ?disabled=${this._loadingScreenshots.has(path)}
                    @click=${() => this._handleScreenshotSelect(path)}
                  >
                    ${this._loadingScreenshots.has(path) ? 'Loading...' : `Open shot ${i + 1}`}
                  </button>
                `)}
              </div>
            ` : nothing}
            ${item.imageBase64 ? html`
              <img
                class="timeline-image"
                alt="Android screenshot"
                src="data:image/png;base64,${item.imageBase64}"
              />
            ` : nothing}
            ${this._selectedScreenshotPath
              && item.screenshotPaths?.includes(this._selectedScreenshotPath)
              && this._screenshotCache.has(this._selectedScreenshotPath) ? html`
              <img
                class="timeline-image"
                alt="Android screenshot"
                src="data:image/png;base64,${this._screenshotCache.get(this._selectedScreenshotPath)}"
              />
            ` : nothing}
          </div>
        `)}
      </div>
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
          ${this._renderTimelineItems()}
        </div>

        <div class="thread-footer">
          <div class="footer-left">
            <span>${this._messages.length} message${this._messages.length !== 1 ? 's' : ''}</span>
            ${jorb?.metrics ? html`
              <div class="footer-metrics">
                <div class="metric-item">
                  <span class="metric-value">${this._formatTokens(jorb.metrics.tokens_used)}</span>
                  <span>tokens</span>
                </div>
                <div class="metric-item">
                  <span class="metric-value">${this._formatCost(jorb.metrics.estimated_cost)}</span>
                  <span>cost</span>
                </div>
              </div>
            ` : nothing}
          </div>
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
