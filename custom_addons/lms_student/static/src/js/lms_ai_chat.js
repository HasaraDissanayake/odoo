/** @odoo-module **/
/**
 * LMS AI Chat Widget — powered by Google Gemini
 * Floating assistant available on all LMS backend pages.
 */

import { registry } from "@web/core/registry";

// ── helpers ──────────────────────────────────────────────────────────────────

function formatResponse(text) {
    // basic markdown-lite: **bold**, newlines
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

async function geminiRpc(message, history) {
    const res = await fetch('/lms/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            jsonrpc: '2.0',
            method: 'call',
            id: Date.now(),
            params: { message, history },
        }),
    });
    const data = await res.json();
    return data.result || { response: 'No response received.', error: true };
}

// ── widget builder ────────────────────────────────────────────────────────────

function buildWidget() {
    // Avoid double-mounting
    if (document.getElementById('lms-ai-btn')) return;

    // ── floating button ──
    const btn = document.createElement('button');
    btn.id = 'lms-ai-btn';
    btn.title = 'LMS AI Assistant';
    btn.innerHTML = '✨';
    document.body.appendChild(btn);

    // ── panel ──
    const panel = document.createElement('div');
    panel.id = 'lms-ai-panel';
    panel.innerHTML = `
        <div id="lms-ai-header">
            <div class="lms-ai-avatar">🤖</div>
            <div class="lms-ai-title">
                <strong>LMS AI Assistant</strong>
                <span>Powered by Gemini</span>
            </div>
            <button id="lms-ai-close" title="Close">✕</button>
        </div>
        <div id="lms-ai-messages">
            <div class="lms-ai-welcome">
                <p style="margin-bottom:8px;font-size:13px;color:#875A7B;">
                    👋 Hi! I'm your LMS AI assistant.<br>Ask me anything about your courses, grades, or attendance.
                </p>
                <div id="lms-ai-chips"></div>
            </div>
        </div>
        <div id="lms-ai-footer">
            <textarea id="lms-ai-input" rows="1" placeholder="Ask me anything…"></textarea>
            <button id="lms-ai-send" title="Send">➤</button>
        </div>
    `;
    document.body.appendChild(panel);

    // ── state ──
    const history = [];
    const messagesEl = panel.querySelector('#lms-ai-messages');
    const input = panel.querySelector('#lms-ai-input');
    const sendBtn = panel.querySelector('#lms-ai-send');
    const chipsEl = panel.querySelector('#lms-ai-chips');

    // ── quick-start chips ──
    const chips = [
        'What is my attendance?',
        'Show my recent grades',
        'Am I at risk?',
        'Which students need help?',
    ];
    chips.forEach(text => {
        const chip = document.createElement('span');
        chip.className = 'lms-ai-chip';
        chip.textContent = text;
        chip.addEventListener('click', () => sendMessage(text));
        chipsEl.appendChild(chip);
    });

    // ── open / close ──
    btn.addEventListener('click', () => {
        panel.classList.toggle('lms-ai-open');
        if (panel.classList.contains('lms-ai-open')) {
            input.focus();
        }
    });

    panel.querySelector('#lms-ai-close').addEventListener('click', (e) => {
        e.stopPropagation();
        panel.classList.remove('lms-ai-open');
    });

    // ── auto-resize textarea ──
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 80) + 'px';
    });

    // ── send on Enter (Shift+Enter = new line) ──
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input.value);
        }
    });

    sendBtn.addEventListener('click', () => sendMessage(input.value));

    // ── message rendering ──
    function appendMessage(role, html, isError = false) {
        const welcome = messagesEl.querySelector('.lms-ai-welcome');
        if (welcome) welcome.remove();

        const msg = document.createElement('div');
        msg.className = 'lms-ai-msg ' + role + (isError ? ' error' : '');
        msg.innerHTML = html;
        messagesEl.appendChild(msg);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return msg;
    }

    function showTyping() {
        const el = document.createElement('div');
        el.className = 'lms-ai-typing';
        el.id = 'lms-ai-typing';
        el.innerHTML = '<span></span><span></span><span></span>';
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function hideTyping() {
        const el = document.getElementById('lms-ai-typing');
        if (el) el.remove();
    }

    // ── core send logic ──
    async function sendMessage(text) {
        text = (text || '').trim();
        if (!text) return;

        // Reset input
        input.value = '';
        input.style.height = 'auto';
        sendBtn.disabled = true;

        // Show user bubble
        appendMessage('user', text);

        // Record in history
        history.push({ role: 'user', text });

        // Show typing indicator
        showTyping();

        try {
            const result = await geminiRpc(text, history.slice(-8));
            hideTyping();

            if (result.error && !result.response) {
                appendMessage('ai', '⚠️ ' + (result.response || 'Error occurred.'), true);
            } else {
                const formatted = formatResponse(result.response);
                appendMessage('ai', formatted);
                history.push({ role: 'model', text: result.response });
            }
        } catch (err) {
            hideTyping();
            appendMessage(
                'ai',
                '⚠️ Failed to reach the AI service. Please check your connection.',
                true
            );
        } finally {
            sendBtn.disabled = false;
            input.focus();
        }
    }
}

// ── Odoo service registration ─────────────────────────────────────────────────

const lmsAiChatService = {
    start() {
        // Mount after a short delay to ensure the Odoo shell/navbar is ready
        setTimeout(buildWidget, 1500);
    },
};

registry.category("services").add("lms_ai_chat_service", lmsAiChatService);
