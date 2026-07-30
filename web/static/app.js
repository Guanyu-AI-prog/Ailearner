marked.setOptions({ breaks: true, gfm: true });

const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const quickBar = document.getElementById('quick-bar');
let isStreaming = false;
let sessionId = localStorage.getItem('ailearner_session_id') || Math.random().toString(36).substring(2, 15);
localStorage.setItem('ailearner_session_id', sessionId);
let currentAssistantDiv = null;
let currentStreamContent = '';
let messageCount = 0;
let radarChartRendered = false;

/* ===== 输入框自动增高 ===== */
function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
}

/* ===== 发送按钮状态 ===== */
function toggleSend() {
    const hasContent = userInput.value.trim().length > 0;
    sendBtn.disabled = !hasContent || isStreaming;
}

/* ===== 快捷发送 ===== */
function quickSend(text) {
    userInput.value = text;
    toggleSend();
    sendMessage();
}

/* ===== 回车发送 ===== */
function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

/* ===== 创建消息气泡 ===== */
function addUserMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'msg msg-user msg-appear';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.textContent = text;

    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
}

function createAssistantMessage() {
    const wrapper = document.createElement('div');
    wrapper.className = 'msg msg-ai msg-appear';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    const dots = document.createElement('div');
    dots.className = 'typing-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';
    bubble.appendChild(dots);

    const time = document.createElement('span');
    time.className = 'msg-time';

    wrapper.appendChild(bubble);
    wrapper.appendChild(time);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
    return { wrapper, bubble, time };
}

function updateAssistantContent(bubble, text, append = false) {
    const dots = bubble.querySelector('.typing-dots');
    if (dots) dots.remove();

    if (append) {
        currentStreamContent += text;
    } else {
        currentStreamContent = text;
    }
    bubble.innerHTML = DOMPurify.sanitize(marked.parse(currentStreamContent));
    scrollToBottom();
}

function finalizeAssistantContent(bubble, timeEl) {
    const dots = bubble.querySelector('.typing-dots');
    if (dots) dots.remove();
    if (currentStreamContent) {
        bubble.innerHTML = DOMPurify.sanitize(marked.parse(currentStreamContent));
    }
    // 显示时间
    const now = new Date();
    timeEl.textContent = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;
    currentStreamContent = '';
    isStreaming = false;
    sendBtn.disabled = true;
    userInput.value = '';
    userInput.style.height = 'auto';
    userInput.focus();
    scrollToBottom();
    // 评测完成后检查是否需要渲染雷达图
    checkAndRenderRadar();
}

/* ===== 雷达图渲染 ===== */
async function checkAndRenderRadar() {
    if (radarChartRendered) return;
    try {
        const resp = await fetch(`/api/evaluation/report/${sessionId}`);
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data.evaluation_done || !data.evaluation_scores) return;
        const scores = data.evaluation_scores;
        if (Object.keys(scores).length === 0) return;
        radarChartRendered = true;
        renderRadarChart(scores);
    } catch (e) {
        // 静默失败，不影响正常流程
    }
}

function renderRadarChart(scores) {
    // 维度中文名映射
    const dimNames = {
        learning_fit: '学习适合度',
        time_match: '时间投入匹配度',
        budget_match: '预算匹配度',
        direction_clarity: '方向明确度',
    };

    const indicators = [];
    const values = [];
    for (const [key, name] of Object.entries(dimNames)) {
        indicators.push({ name: name, max: 5 });
        values.push(scores[key] || 0);
    }

    // 创建图表容器
    const wrapper = document.createElement('div');
    wrapper.className = 'msg msg-ai msg-appear';

    const chartContainer = document.createElement('div');
    chartContainer.className = 'radar-chart-container';
    chartContainer.style.width = '100%';
    chartContainer.style.maxWidth = '400px';
    chartContainer.style.height = '320px';
    chartContainer.style.margin = '12px auto';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.style.padding = '8px';
    bubble.appendChild(chartContainer);

    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    scrollToBottom();

    // 使用 ECharts 渲染
    if (typeof echarts === 'undefined') return;
    const chart = echarts.init(chartContainer);
    chart.setOption({
        radar: {
            indicator: indicators,
            shape: 'polygon',
            splitNumber: 5,
            axisName: {
                color: '#64748b',
                fontSize: 13,
            },
            splitLine: { lineStyle: { color: '#e2e8f0' } },
            splitArea: { show: true, areaStyle: { color: ['rgba(99,102,241,0.02)', 'rgba(99,102,241,0.05)'] } },
            axisLine: { lineStyle: { color: '#e2e8f0' } },
        },
        series: [{
            type: 'radar',
            data: [{
                value: values,
                name: '你的评分',
                areaStyle: { color: 'rgba(99,102,241,0.2)' },
                lineStyle: { color: '#6366f1', width: 2 },
                itemStyle: { color: '#6366f1' },
                symbol: 'circle',
                symbolSize: 6,
            }],
        }],
        tooltip: {
            trigger: 'item',
            formatter: function (params) {
                const vals = params.value;
                let html = '<strong>你的评分</strong><br/>';
                indicators.forEach((ind, i) => {
                    html += `${ind.name}：${vals[i]}/5<br/>`;
                });
                return html;
            },
        },
    });

    // 响应式
    window.addEventListener('resize', () => chart.resize());
}

/* ===== 菜单 ===== */
function toggleMenu() {
    const dd = document.getElementById('menu-dropdown');
    dd.classList.toggle('show');
}

// 点击外部关闭菜单
document.addEventListener('click', (e) => {
    const dd = document.getElementById('menu-dropdown');
    const btn = document.getElementById('menu-btn');
    if (dd && !dd.contains(e.target) && !btn.contains(e.target)) {
        dd.classList.remove('show');
    }
});

function resetChat() {
    document.getElementById('menu-dropdown').classList.remove('show');
    // 清空消息区，只留欢迎消息
    chatMessages.innerHTML = '';
    messageCount = 0;
    radarChartRendered = false;
    quickBar.style.display = '';
    // 重新显示欢迎消息
    const welcome = document.createElement('div');
    welcome.className = 'msg msg-ai msg-appear';
    welcome.innerHTML = `
        <div class="msg-bubble">
            <p>对话已重置 ✨</p>
            <p>有什么想聊的？</p>
        </div>
        <span class="msg-time">刚刚</span>
    `;
    chatMessages.appendChild(welcome);
    // 重置服务端会话
    fetch(`/api/session/${sessionId}/reset`, { method: 'POST' }).catch(() => {});
    sessionId = Math.random().toString(36).substring(2, 15);
    localStorage.setItem('ailearner_session_id', sessionId);
}

function showAbout() {
    document.getElementById('menu-dropdown').classList.remove('show');
    const msg = document.createElement('div');
    msg.className = 'msg msg-ai msg-appear';
    msg.innerHTML = `
        <div class="msg-bubble">
            <p><strong>AI 学习引路人</strong> v1.0</p>
            <p>帮你判断该不该学 AI、学什么方向、怎么零成本入门。</p>
            <p>基于标签路由 + LLM 对话，无需向量数据库。</p>
        </div>
        <span class="msg-time">系统</span>
    `;
    chatMessages.appendChild(msg);
    scrollToBottom();
}

/* ===== 滚动到底部 ===== */
function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/* ===== 发送消息 ===== */
async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isStreaming) return;

    // 隐藏快捷回复
    messageCount++;
    if (messageCount >= 1) {
        quickBar.style.display = 'none';
    }

    addUserMessage(text);

    isStreaming = true;
    sendBtn.disabled = true;

    const { wrapper, bubble, time } = createAssistantMessage();
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
                            updateAssistantContent(bubble, parsed.text, true);
                        } else if (parsed.type === 'status') {
                            // 状态信息追加到气泡底部
                            let statusEl = bubble.querySelector('.msg-status');
                            if (!statusEl) {
                                statusEl = document.createElement('div');
                                statusEl.className = 'msg-status';
                                bubble.appendChild(statusEl);
                            }
                            statusEl.textContent = parsed.text.replace(/[*>\n]/g, '').trim();
                            scrollToBottom();
                        }
                    } catch (e) {
                        console.warn('Parse error:', e, data);
                    }
                }
            }
        }
    } catch (err) {
        const errP = document.createElement('p');
        errP.style.color = '#ef4444';
        errP.textContent = `出错了：${err.message}。请重试。`;
        bubble.appendChild(errP);
    }

    finalizeAssistantContent(bubble, time);
}
