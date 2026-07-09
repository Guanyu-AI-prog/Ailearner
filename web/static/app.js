marked.setOptions({ breaks: true, gfm: true });

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
    contentDiv.innerHTML = marked.parse(content);
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
    const typing = contentDiv.querySelector('.typing-indicator');
    if (typing) typing.remove();

    if (append) {
        currentStreamContent += text;
    } else {
        currentStreamContent = text;
    }
    contentDiv.innerHTML = marked.parse(currentStreamContent);
    scrollToBottom();
}

function finalizeAssistantContent(contentDiv) {
    const typing = contentDiv.querySelector('.typing-indicator');
    if (typing) typing.remove();
    if (currentStreamContent) {
        contentDiv.innerHTML = marked.parse(currentStreamContent);
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
