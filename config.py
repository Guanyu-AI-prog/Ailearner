import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)

class Config:
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "siliconflow").lower()

    SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")

    # 最终生效的 LLM 配置（优先级：手动指定 > 当前 provider 配置）
    _manual_key = os.getenv("LLM_API_KEY", "")
    _manual_url = os.getenv("LLM_BASE_URL", "")
    _manual_model = os.getenv("LLM_MODEL", "")

    if LLM_PROVIDER == "deepseek":
        LLM_API_KEY = _manual_key or DEEPSEEK_API_KEY
        LLM_BASE_URL = _manual_url or DEEPSEEK_BASE_URL
        LLM_MODEL = _manual_model or DEEPSEEK_MODEL
    else:
        LLM_API_KEY = _manual_key or SILICONFLOW_API_KEY
        LLM_BASE_URL = _manual_url or "https://api.siliconflow.cn/v1"
        LLM_MODEL = _manual_model or "deepseek-ai/DeepSeek-V4-Flash"

    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

    KNOWLEDGE_DIR = ROOT_DIR / os.getenv("KNOWLEDGE_DIR", "knowledge/data")

    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))

    EVALUATION_FIRST_QUESTION = {
        "id": "path",
        "question": "你想「学 AI」还是「用 AI」？",
        "options": [
            "学 AI：深入技术，理解原理，想自己训练/微调模型",
            "用 AI：把 AI 当工具提高效率，不想深究底层",
        ]
    }

    LEARN_AI_QUESTIONS = [
        {
            "id": "goal",
            "question": "你学 AI 是为了什么？",
            "options": [
                "想转行做 AI 相关工作",
                "想用 AI 提升现在的工作效率",
                "做学术研究",
                "纯粹好奇/兴趣",
                "还没想清楚，先了解看看"
            ]
        },
        {
            "id": "background",
            "question": "你目前的职业或专业背景是什么？",
            "options": [
                "计算机/IT 相关",
                "理工科（非计算机）",
                "文科/商科/艺术",
                "学生（请说明年级和专业）",
                "其他"
            ]
        },
        {
            "id": "time",
            "question": "你每周大概能投入多少时间学习 AI？",
            "options": [
                "少于 2 小时",
                "2-5 小时",
                "5-10 小时",
                "10 小时以上"
            ]
        },
        {
            "id": "math_level",
            "question": "你目前的数学基础怎么样？",
            "options": [
                "高中数学水平",
                "大学学过高等数学/线性代数（还记得一些）",
                "大学学过高等数学/线性代数（基本忘了）",
                "数学基础很好，能看懂公式推导",
                "对数学没信心"
            ]
        },
        {
            "id": "programming_level",
            "question": "你目前的编程基础怎么样？",
            "options": [
                "零基础，没写过代码",
                "能看懂一些 Python 代码，但自己写不了",
                "会写基本的 Python 代码",
                "有丰富的编程经验"
            ]
        },
        {
            "id": "budget",
            "question": "你愿意为学习 AI 投入多少预算？",
            "options": [
                "零成本，只用免费资源",
                "少量预算（1000 元以内）",
                "愿意花钱买课/算力（几千到上万）",
                "公司/学校报销，预算充足"
            ]
        },
        {
            "id": "direction",
            "question": "你对 AI 的哪个方向最感兴趣？",
            "options": [
                "文字相关（ChatGPT/写作/翻译/NLP）",
                "图像相关（绘画/设计/视频生成/CV）",
                "数据分析/预测",
                "声音相关（语音合成/识别）",
                "AI 产品设计/项目管理",
                "还没特定方向，想全面了解"
            ]
        }
    ]

    USE_AI_SCENARIOS = [
        {
            "id": "article_edit",
            "name": "文章修改 / 润色 / 重写",
            "prompt": "你是一位资深编辑，擅长把握语气和风格。请帮我{task}以下文章。\n\n## 要求\n- 保持原文的核心信息不变\n- 让语言更流畅自然\n- 语气：{tone}\n- 字数：{word_count}\n- 目标读者：{audience}\n\n## 原文\n\n{text}\n\n请直接输出{task}后的结果，不要加额外说明。",
            "parameters": {
                "task": ["修改", "润色", "重写"],
                "tone": ["正式", "半正式", "亲切", "幽默"],
                "word_count": "不超过 X 字 / 不限制 / 精简到 X 字",
                "audience": "目标读者描述（如：领导、客户、普通读者）",
                "text": "你的文章内容"
            },
            "advice": "把原文粘贴到 {text} 位置，调整 {task} 和 {tone} 就能直接用了。对 ChatGPT / Claude / DeepSeek 都适用。"
        },
        {
            "id": "doc_summary",
            "name": "文档总结 / 提炼核心",
            "prompt": "请帮我总结以下文档。\n\n## 要求\n- 提取核心观点和关键数据\n- 控制在 {length} 以内\n- 列出 3-5 个要点\n- 指出可能的行动建议\n\n## 文档\n\n{text}\n\n请以「要点列表 + 一句话总结」的格式输出。",
            "parameters": {
                "length": ["300 字", "500 字", "1000 字", "一页 PPT 的篇幅"],
                "text": "你的文档内容"
            },
            "advice": "适合会议纪要、论文、长篇报告的总结。把要总结的内容粘贴到 {text} 位置即可。"
        },
        {
            "id": "email_writing",
            "name": "邮件 / 公文写作",
            "prompt": "帮我写一封{type}。\n\n## 场景\n- 收件人：{recipient}\n- 目的：{purpose}\n- 语气：{tone}\n- 我方的身份：{identity}\n- 必须包含的信息：{must_include}\n\n## 额外要求\n{extra}\n\n请写出完整的{type}，包含标题和正文。",
            "parameters": {
                "type": ["邮件", "通知", "汇报", "申请", "感谢信"],
                "recipient": "收件人/部门",
                "purpose": "写这封邮件/公文的目的",
                "tone": ["正式", "半正式", "亲切"],
                "identity": "你的身份",
                "must_include": "必须提到的关键信息",
                "extra": "其他补充要求（如：附件说明、截止日期等）"
            },
            "advice": "说清楚收件人和目的，语气选对，AI 就能写出 80 分以上的初稿。"
        },
        {
            "id": "translation",
            "name": "翻译",
            "prompt": "请将以下内容从{source_lang}翻译成{target_lang}。\n\n## 要求\n- 保持原文的语气和风格\n- 专业术语使用{domain}领域的标准译法\n- 符合目标语言的表达习惯\n- 如果原文有歧义，加注释说明\n\n## 原文\n\n{text}\n\n直接输出翻译结果即可。",
            "parameters": {
                "source_lang": ["中文", "英文", "日文", "韩文", "法文"],
                "target_lang": ["中文", "英文", "日文", "韩文", "法文"],
                "domain": "领域（如：技术、法律、医学、营销）",
                "text": "待翻译的内容"
            },
            "advice": "指定领域（domain）能大幅提高专业术语的翻译准确度。"
        },
        {
            "id": "data_analysis",
            "name": "数据分析 / 报告生成",
            "prompt": "请分析以下数据。\n\n## 背景\n{background}\n\n## 数据\n{data}\n\n## 要求\n- 找出关键趋势和异常点\n- 用表格呈现核心指标\n- 给出数据支持的 actionable 建议\n- 假设阅读者是：{audience}\n\n先列出核心发现，再展开分析。",
            "parameters": {
                "background": "数据背景说明",
                "data": "你要分析的数据（表格/文本/CSV）",
                "audience": ["技术团队", "管理层", "非技术背景的决策者", "客户"]
            },
            "advice": "把原始数据贴进去就行，AI 能从表格、CSV、甚至描述性文本中提取信息。"
        },
        {
            "id": "creative_writing",
            "name": "创意写作 / 文案",
            "prompt": "请帮我写一个{genre}。\n\n## 基本信息\n- 主题：{topic}\n- 风格：{style}\n- 篇幅：{length}\n- 目标读者：{audience}\n\n## 关键词（必须包含）\n{keywords}\n\n## 参考 / 灵感（如果有）\n{reference}\n\n请直接输出创作内容。",
            "parameters": {
                "genre": ["故事", "广告文案", "标题", "口号", "宣传文案", "剧本片段"],
                "topic": "创作主题",
                "style": ["幽默", "严肃", "温暖", "专业", "文艺", "极简"],
                "length": "篇幅要求",
                "audience": "目标读者",
                "keywords": "必须包含的关键词或短语",
                "reference": "参考内容或灵感（可选）"
            },
            "advice": "不要只给 1 个版本，可以要求 AI 给你 3 个不同风格的版本对比选。"
        },
        {
            "id": "tutoring",
            "name": "学习辅导 / 答疑",
            "prompt": "我正在学习{topic}。请帮我：\n\n1. 用最简单的语言解释{concept}\n2. 给一个生活中的类比帮助理解\n3. 出 3 道自测题（附答案）\n4. 推荐下一步学什么\n\n我的基础：{level}\n\n请用通俗易懂的方式回答，避免过多专业术语。",
            "parameters": {
                "topic": "正在学习的主题",
                "concept": "想理解的概念",
                "level": ["零基础", "初级", "中级", "高级"]
            },
            "advice": "适合任何学科的学习，让 AI 变成你的私人导师。觉得讲太快了就说「再简单一点」。"
        },
        {
            "id": "coding_helper",
            "name": "编程辅助",
            "prompt": "请帮我{task}。\n\n## 背景\n- 编程语言：{language}\n- 我目前的水平：{level}\n\n## 需求\n{requirement}\n\n## 已有代码（如果有）\n{existing_code}\n\n请先给出方案思路，再提供完整代码，最后说明如何运行和测试。",
            "parameters": {
                "task": ["写一段代码", "解释这段代码", "调试这个错误", "重构这段代码", "加注释和文档"],
                "language": "编程语言",
                "level": ["零基础", "能看懂", "能写简单", "有经验"],
                "requirement": "需求描述",
                "existing_code": "已有代码（可选）"
            },
            "advice": "零基础也能用，让 AI 写代码然后你复制运行就行。"
        }
    ]

    USE_AI_QUESTIONS = [
        {
            "id": "usage_time",
            "question": "你每天大概花多少时间在AI上？",
            "options": [
                "偶尔试一下",
                "每天用一点",
                "经常用",
                "重度依赖"
            ]
        },
        {
            "id": "current_tools",
            "question": "你现在用什么工具？",
            "options": [
                "ChatGPT",
                "文心一言",
                "通义千问",
                "Kimi",
                "其他",
                "没用过"
            ]
        }
    ]

    EVALUATION_QUESTIONS = [EVALUATION_FIRST_QUESTION] + LEARN_AI_QUESTIONS

config = Config()
