const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
let isStreaming = false;
let sessionId = Math.random().toString(36).substring(2, 15);
let currentAssistantDiv = null;
let currentStreamContent = '';

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function addMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = renderMarkdown(content);
    div.appendChild(contentDiv);
    chatMessages.appendChild(div);
    scrollToBottom();
    return div;
}

function createAssistantMessage() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    // Add typing indicator
    const typing = document.createElement('div');
    typing.className = 'typing-indicator';
    typing.innerHTML = '<span></span><span></span><span></span>';
    contentDiv.appendChild(typing);
    div.appendChild(contentDiv);
    chatMessages.appendChild(div);
    scrollToBottom();
    return { div, contentDiv, typing };
}

function updateAssistantContent(contentDiv, text, append = false) {
    // Remove typing indicator
    const typing = contentDiv.querySelector('.typing-indicator');
    if (typing) typing.remove();

    if (append) {
        currentStreamContent += text;
    } else {
        currentStreamContent = text;
    }
    contentDiv.innerHTML = renderMarkdown(currentStreamContent);
    scrollToBottom();
}

function finalizeAssistantContent(contentDiv) {
    const typing = contentDiv.querySelector('.typing-indicator');
    if (typing) typing.remove();
    if (currentStreamContent) {
        contentDiv.innerHTML = renderMarkdown(currentStreamContent);
    }
    currentStreamContent = '';
    isStreaming = false;
    sendBtn.disabled = false;
    sendBtn.textContent = '发送';
    userInput.focus();
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isStreaming) return;

    userInput.value = '';
    addMessage('user', text);

    isStreaming = true;
    sendBtn.disabled = true;
    sendBtn.textContent = '...';

    const { div, contentDiv, typing } = createAssistantMessage();
    currentStreamContent = '';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, message: text }),
        });

        if (!response.ok) throw new Error('请求失败');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.trim()) continue;
                if (line.startsWith('data: ')) {
                    const data = line.slice(6).trim();
                    if (!data) continue;
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.type === 'content') {
                            updateAssistantContent(contentDiv, parsed.text, true);
                        } else if (parsed.type === 'status') {
                            // Show status messages in a smaller style
                            const statusDiv = contentDiv.querySelector('.status-info') || document.createElement('div');
                            statusDiv.className = 'status-info';
                            statusDiv.style.cssText = 'font-size: 0.85em; color: #6c757d; margin: 8px 0;';
                            statusDiv.textContent = parsed.text.replace(/[*>\n]/g, '').trim();
                            contentDiv.appendChild(statusDiv);
                            scrollToBottom();
                        }
                    } catch (e) {
                        console.warn('Parse error:', e, data);
                    }
                }
            }
        }
    } catch (err) {
        contentDiv.innerHTML = `<p>出错了：${err.message}。请重试。</p>`;
    }

    finalizeAssistantContent(contentDiv);
}

function renderMarkdown(text) {
    if (!text) return '';

    // Escape HTML
    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Images
    text = text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%">');
    // Links
    text = text.replace(/\[([^\]]*)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // Headers
    text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');

    // Bold and italic
    text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Inline code
    text = text.replace(/`(.+?)`/g, '<code>$1</code>');

    // Horizontal rules
    text = text.replace(/^---$/gm, '<hr>');

    // Unordered lists
    text = text.replace(/^- (.+)$/gm, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // Ordered lists
    text = text.replace(/^\d+\.\s(.+)$/gm, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>\n?)+/g, (match) => {
        return match.startsWith('<ul>') ? match : '<ol>' + match + '</ol>';
    });

    // Fix nested list issue
    text = text.replace(/<\/ul>\n?<ul>/g, '');
    text = text.replace(/<\/ol>\n?<ol>/g, '');

    // Line breaks - double newline = paragraph
    text = text.replace(/\n\n/g, '</p><p>');

    // Single newline = <br>
    text = text.replace(/\n/g, '<br>');

    // Wrap in paragraph if not already
    if (!text.startsWith('<h') && !text.startsWith('<ul') && !text.startsWith('<ol') && !text.startsWith('<hr')) {
        text = '<p>' + text + '</p>';
    }

    // Clean up empty paragraphs
    text = text.replace(/<p><\/p>/g, '');

    return text;
}
