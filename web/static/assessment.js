(() => {
    "use strict";

    const root = document.getElementById("assessment-root");
    if (!root) return;

    const CACHE_KEY = "ailearner_structured_assessment_answers_v1";
    const PENDING_KEY = "ailearner_structured_assessment_pending_v1";
    const SESSION_KEY = "ailearner_session_id";
    const page = root.dataset.assessmentPage;
    const assessmentId = root.dataset.assessmentId;
    const generatedSessionId = window.crypto?.randomUUID?.() || Math.random().toString(36).slice(2);
    const sessionId = localStorage.getItem(SESSION_KEY) || generatedSessionId;
    localStorage.setItem(SESSION_KEY, sessionId);

    function escapeHtml(value) {
        const element = document.createElement("div");
        element.textContent = String(value);
        return element.innerHTML;
    }

    function navigate(path) {
        window.location.assign(path);
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, options);
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail || "请求失败，请稍后重试。");
        }
        return response.json();
    }

    function entryPage() {
        root.innerHTML = `
            <div class="assessment-hero">
                <span class="eyebrow">AI LEARNING ASSESSMENT</span>
                <h1>AI 零基础能力标准化测评</h1>
                <p>30 秒完成测评，获得清晰的能力定位与专属 AI 学习路径。</p>
                <div class="assessment-actions">
                    <button class="btn btn-primary" id="start-assessment">开始测评</button>
                    <a class="btn btn-secondary" href="/assessment/history">查看历史记录</a>
                </div>
                <dl class="assessment-facts">
                    <div><dt>10</dt><dd>道固定单选题</dd></div>
                    <div><dt>4</dt><dd>项能力维度</dd></div>
                    <div><dt>1</dt><dd>份结构化报告</dd></div>
                </dl>
            </div>`;
        document.getElementById("start-assessment").addEventListener("click", () => {
            localStorage.removeItem(CACHE_KEY);
            navigate("/assessment/quiz");
        });
    }

    function loadCachedAnswers() {
        try {
            return JSON.parse(localStorage.getItem(CACHE_KEY) || "{}");
        } catch {
            return {};
        }
    }

    function saveCachedAnswers(answers) {
        localStorage.setItem(CACHE_KEY, JSON.stringify(answers));
    }

    async function quizPage() {
        const { questions } = await requestJson("/api/assessments/questions");
        const answers = loadCachedAnswers();
        let index = 0;

        function render() {
            const question = questions[index];
            const selected = answers[question.id] || "";
            const isLast = index === questions.length - 1;
            root.innerHTML = `
                <div class="quiz-card">
                    <a class="back-link" href="/assessment">← 返回测评首页</a>
                    <div class="quiz-progress-row">
                        <span>第 ${index + 1} 题 / 共 ${questions.length} 题</span>
                        <span>${Math.round(((index + 1) / questions.length) * 100)}%</span>
                    </div>
                    <div class="quiz-progress"><span style="width:${((index + 1) / questions.length) * 100}%"></span></div>
                    <p class="question-dimension">${escapeHtml(question.dimension)}</p>
                    <h1>${escapeHtml(question.question)}</h1>
                    <div class="option-list">
                        ${question.options.map((option) => `
                            <button class="option-button ${selected === option.key ? "selected" : ""}" data-answer="${option.key}">
                                <span>${option.key}</span>${escapeHtml(option.text)}
                            </button>`).join("")}
                    </div>
                    <p class="quiz-error" id="quiz-error" aria-live="polite"></p>
                    <div class="quiz-actions">
                        <button class="btn btn-secondary" id="previous-question" ${index === 0 ? "disabled" : ""}>上一题</button>
                        <button class="btn btn-primary" id="next-question">${isLast ? "提交测评" : "下一题"}</button>
                    </div>
                </div>`;

            root.querySelectorAll("[data-answer]").forEach((button) => {
                button.addEventListener("click", () => {
                    answers[question.id] = button.dataset.answer;
                    saveCachedAnswers(answers);
                    render();
                });
            });
            document.getElementById("previous-question").addEventListener("click", () => {
                index -= 1;
                render();
            });
            document.getElementById("next-question").addEventListener("click", () => {
                if (!answers[question.id]) {
                    document.getElementById("quiz-error").textContent = "请选择当前题目答案。";
                    return;
                }
                if (isLast) {
                    const complete = questions.every((item) => answers[item.id]);
                    if (!complete) {
                        document.getElementById("quiz-error").textContent = "请完成全部题目后再提交。";
                        return;
                    }
                    localStorage.setItem(PENDING_KEY, JSON.stringify({ sessionId, answers }));
                    navigate("/assessment/loading");
                    return;
                }
                index += 1;
                render();
            });
        }
        render();
    }

    async function loadingPage() {
        root.innerHTML = `
            <div class="loading-card">
                <div class="loading-orbit" aria-hidden="true"></div>
                <h1>正在生成专属学习报告</h1>
                <p>正在分析你的结构化答卷，请不要关闭此页面。</p>
                <p class="loading-status" id="loading-status"></p>
            </div>`;
        const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || localStorage.getItem(PENDING_KEY) || "null");
        if (!pending) {
            navigate("/assessment/quiz");
            return;
        }
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), 30000);
        try {
            const data = await requestJson("/api/assessments", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: pending.sessionId, answers: Object.entries(pending.answers).map(([question_id, answer]) => ({ question_id, answer })) }),
                signal: controller.signal,
            });
            localStorage.removeItem(PENDING_KEY);
            localStorage.removeItem(CACHE_KEY);
            navigate(`/assessment/report/${data.id}`);
        } catch (error) {
            const message = error.name === "AbortError" ? "生成超时，请返回后重试。" : error.message;
            document.getElementById("loading-status").textContent = message;
            root.insertAdjacentHTML("beforeend", '<a class="btn btn-secondary" href="/assessment/quiz">返回答题页</a>');
        } finally {
            window.clearTimeout(timer);
        }
    }

    function reportSections(report) {
        const dimensions = report.dimensions.map((item) => `
            <article class="dimension-card">
                <div><span>${escapeHtml(item.name)}</span><strong>${item.score}</strong></div>
                <div class="score-bar"><span style="width:${item.score}%"></span></div>
                <p>${escapeHtml(item.analysis)}</p>
            </article>`).join("");
        const list = (items) => `<ol>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`;
        return `
            <section class="report-section"><h2>四大维度分析</h2><div class="dimension-grid">${dimensions}</div></section>
            <section class="report-section"><h2>短期学习规划</h2>${list(report.short_term_plan)}</section>
            <section class="report-section"><h2>进阶学习路线</h2>${list(report.learning_path)}</section>
            <section class="report-section report-warning"><h2>避坑建议</h2>${list(report.pitfalls)}</section>`;
    }

    async function reportPage() {
        const assessment = await requestJson(`/api/assessments/${assessmentId}`);
        const { report } = assessment;
        root.innerHTML = `
            <div class="report-page">
                <section class="report-summary">
                    <span class="eyebrow">ASSESSMENT REPORT</span>
                    <h1>${escapeHtml(report.level)} AI 学习者</h1>
                    <div class="score-number">${report.overall_score}<small>/100</small></div>
                    <p>${escapeHtml(report.positioning)}</p>
                    <div class="assessment-actions">
                        <a class="btn btn-primary" href="/assessment/quiz">重新测评</a>
                        <a class="btn btn-secondary" href="/assessment/history">查看历史记录</a>
                        <a class="btn btn-secondary" href="/chat">返回聊天首页</a>
                    </div>
                </section>
                ${reportSections(report)}
            </div>`;
    }

    async function historyPage() {
        const { items } = await requestJson(`/api/assessments/history/${encodeURIComponent(sessionId)}`);
        const rows = items.length ? items.map((item) => `
            <article class="history-item">
                <div><strong>${escapeHtml(item.level)}</strong><span>${escapeHtml(item.created_at)}</span></div>
                <div class="history-score">${item.overall_score}</div>
                <div class="history-actions">
                    <a href="/assessment/report/${item.id}">查看报告</a>
                    <button data-delete-id="${item.id}">删除</button>
                </div>
            </article>`).join("") : '<div class="empty-state">暂无测评记录，完成第一次测评后将在这里显示。</div>';
        root.innerHTML = `
            <div class="history-page">
                <div class="history-heading"><div><span class="eyebrow">HISTORY</span><h1>我的测评记录</h1></div><button class="btn btn-secondary" id="clear-history" ${items.length ? "" : "disabled"}>清空记录</button></div>
                <div class="history-list">${rows}</div>
                <a class="btn btn-primary" href="/assessment">开始新的测评</a>
            </div>`;
        root.querySelectorAll("[data-delete-id]").forEach((button) => {
            button.addEventListener("click", async () => {
                if (!window.confirm("确认删除这条测评记录吗？")) return;
                await requestJson(`/api/assessments/${button.dataset.deleteId}?session_id=${encodeURIComponent(sessionId)}`, { method: "DELETE" });
                historyPage();
            });
        });
        document.getElementById("clear-history").addEventListener("click", async () => {
            if (!window.confirm("确认清空全部测评记录吗？")) return;
            await requestJson(`/api/assessments/history/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
            historyPage();
        });
    }

    const handlers = { entry: entryPage, quiz: quizPage, loading: loadingPage, report: reportPage, history: historyPage };
    handlers[page]().catch((error) => {
        root.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}<br><a href="/assessment">返回测评首页</a></div>`;
    });
})();
