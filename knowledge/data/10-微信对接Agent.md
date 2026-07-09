# 微信对接AI Agent：20分钟搞定

> 已验证的零成本方案，从0到微信里有个AI助手，只需20分钟。

---

## 一句话流程

**免费领无影云电脑 → 选择 Hermes 镜像 → 配置 MiMo API Key → 对接微信 → 完成**

全程无需安装任何软件，无影云电脑预装 Hermes 镜像，开箱即用。

---

## 详细步骤

### 第一步：免费领无影云电脑（5分钟）

1. 访问阿里云无影云电脑官网，新用户免费领取1个月（4核8G）
2. 创建云电脑时，选择 **Hermes 镜像**（预装 Hermes Agent 和运行环境）
3. 使用手机/旧笔记本/平板远程连接，和本地电脑一样用

> 电脑配置不够？无影云电脑就是你的解决方案。4核8G足够跑 Agent，免费一个月。

### 第二步：获取 MiMo API Key（5分钟）

1. 打开 https://platform.xiaomimimo.com?ref=A4BGLM
2. 注册账号，邀请码自动填入 **A4BGLM**
3. 双方各得 ¥10 API 体验金 + 首单 9 折
4. 进入控制台 → 创建 API Key

> 不需要自己买模型，MiMo 的免费额度够用很久。

### 第三步：配置对接微信（10分钟）

在无影云电脑里执行：

```bash
# 配置 MiMo API Key（Hermes 镜像已预装，无需安装）
hermes config set api_key "你的MiMo API Key"
hermes config set base_url "https://api.xiaomimimo.com/v1"
hermes config set model "MiMo V2.5"

# 启动微信网关
hermes gateway setup
# 选择 Weixin 模式
# 用手机微信扫码登录
```

扫码完成后，你的微信就接上了 AI。

---

## 完成后你能做什么

- 在微信里直接和 AI 对话
- 设置自动回复规则
- AI 帮你查资料、写文案、翻译
- 后续可扩展：飞书对接、RAG知识库、定时任务

---

## 常见问题

### Q：Hermes 镜像需要单独安装吗？
不需要。无影云电脑选择 Hermes 镜像即预装完成，开机即用。

### Q：MiMo 免费额度够用多久？
¥10 体验金约 7000 万 Tokens，个人日常使用能用很久。

### Q：为什么推荐 MiMo 而不是其他模型？
零成本 + 兼容 OpenAI 格式 + 无需实名认证（部分平台需要），最快路径。

### Q：手机关机了 AI 还能回复吗？
能。Agent 跑在云电脑上，24 小时在线，不受本地设备影响。

### Q：登录态会过期吗？
会。微信 session token 约 7 天过期，需要重新扫码。建议每周检查一次。
