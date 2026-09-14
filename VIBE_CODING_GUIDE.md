# Vibe Coding 操作手册

> 基于 Glean 项目实战经验总结的 AI 辅助编程最佳实践

---

## 📖 什么是 Vibe Coding

Vibe Coding 是一种与 AI 协作编程的工作模式，通过清晰的沟通和规范的流程，让 AI 成为高效的编程助手，同时保持代码质量和项目可控性。

---

## 🎯 核心原则

### 1. 信任但验证（Trust but Verify）
- ✅ 相信 AI 的能力，但每一步都要人工验证
- ✅ AI 是助手，你是项目的 Owner

### 2. 小步快跑，快速反馈
- ✅ 每次只让 AI 完成一个小任务
- ✅ 立即测试，立即反馈，立即 commit

### 3. 文档先行
- ✅ 先让 AI 生成计划，你审核后再执行
- ✅ 保持文档与代码同步

---

## 🚀 开始新项目

### Step 1: 技术栈选择

**你需要做的**：
```
告诉 AI：
"我要做一个 [项目描述]，
主要功能是：
1. xxx
2. yyy
3. zzz

请推荐技术栈，并说明选择理由。"
```

**你需要决定**：
- 前端框架（React/Vue/...）
- 后端框架（FastAPI/Express/...）
- 数据库（SQLite/PostgreSQL/...）
- 是否使用 TypeScript

**关键决策点**：
- ✅ 简单项目：JavaScript + PropTypes
- ✅ 中大型项目：TypeScript
- ✅ 快速原型：SQLite
- ✅ 生产环境：PostgreSQL/MySQL

### Step 2: 项目结构设计

**让 AI 做的**：
```
"基于选定的技术栈，请设计项目目录结构。
要求：
- 前后端分离
- 模块化设计
- 便于扩展

请给出目录树和每个目录的说明。"
```

**你需要审核**：
- 目录结构是否合理
- 是否便于后续维护
- 是否符合团队习惯

### Step 3: 建立规范

**必须创建的文档**：
1. `PROJECT_DOCUMENTATION.md` - 项目总体文档
2. `AI_COLLABORATION_RULES.md` - AI 协作规范
3. `.gitignore` - Git 忽略规则
4. `README.md` - 项目说明

**关键配置**：
```bash
# 代码格式化
npm install --save-dev eslint prettier

# Git hooks（可选）
npm install --save-dev husky lint-staged
```

---

## 🔧 开发阶段

### 功能开发流程

#### 1. 需求明确
```
❌ 不要说：
"帮我做一个用户管理功能"

✅ 要说：
"帮我做一个用户管理功能，需要：
1. 用户列表（分页、搜索、筛选）
2. 添加用户（表单验证）
3. 编辑用户
4. 删除用户（带确认）
5. 用户详情查看

请先给出实现计划。"
```

#### 2. 审核计划
AI 给出计划后，检查：
- [ ] 是否遗漏功能点
- [ ] 是否考虑了错误处理
- [ ] 是否考虑了用户体验
- [ ] 技术方案是否合理

#### 3. 分步实施
```
"计划看起来不错，我们先实现第一步：用户列表。

要求：
- 使用 Ant Design Table 组件
- 支持分页（每页 10 条）
- 支持按用户名搜索
- 显示用户名、邮箱、创建时间、操作列

完成后我会测试，测试通过后再继续下一步。"
```

#### 4. 测试验证
每完成一步：
- [ ] 刷新浏览器测试
- [ ] 检查控制台是否有错误
- [ ] 测试所有交互功能
- [ ] Git commit

```bash
git add .
git commit -m "feat: add user list with pagination and search"
```

---

## 🛡️ 重构阶段

### 重构前准备（关键！）

#### Step 1: 生成功能清单（详细步骤）

**为什么需要功能清单**：
- 你可能记不住所有功能和位置
- AI 重构时容易遗漏功能
- 功能清单是验证的唯一可靠依据

**方法 1：让 AI 一次性扫描（推荐）**

```
"请分析 Dashboard.jsx 文件，生成一份详细的功能清单文档。

对于每个 Tab，请记录：
1. Tab 名称和位置（第几行）
2. 所有按钮及其功能（函数名、位置）
3. 所有表格列（列名、render 函数）
4. 所有输入框/选择器（名称、功能）
5. 所有 props 传递
6. 所有 state 变量
7. 所有事件处理函数
8. 所有 API 调用

格式要求：
- 使用 Markdown 表格
- 包含代码行号
- 包含函数名和简要说明
- 易于对照检查

请将结果保存为 FEATURE_INVENTORY.md 文件。"
```

**功能清单模板示例**：
```markdown
# Dashboard 功能清单（重构前基线）

生成时间：2024-XX-XX
原文件：Dashboard.jsx (1437 行)

---

## Tab 1: 数据管理 (NewsManagementTab)

### 状态变量
| 变量名 | 类型 | 初始值 | 用途 | 行号 |
|--------|------|--------|------|------|
| news | Array | [] | 新闻列表 | L42 |
| pagination | Object | {current:1, total:0} | 分页状态 | L43 |
| filterSource | String | undefined | 来源筛选 | L44 |

### 功能按钮
| 按钮文本 | 事件函数 | 功能说明 | 行号 |
|----------|----------|----------|------|
| 加精 | handleAddToFeatured | 添加到精选 | L156 |
| 删除 | handleDeleteNews | 删除新闻 | L167 |
| 导出 | onShowExport | 导出数据 | L134 |

### 表格列定义
| 列名 | dataIndex | render 函数 | 特殊功能 | 行号 |
|------|-----------|-------------|----------|------|
| ID | id | - | - | L89 |
| 标题 | title | 链接渲染 | - | L90 |
| 操作 | - | 按钮组 | 加精/删除 | L95 |

### API 调用
| 函数名 | API 方法 | 参数 | 返回值 | 行号 |
|--------|----------|------|--------|------|
| fetchNews | getNews | page, limit | Array | L58 |

### Props 接收
| Prop 名 | 类型 | 必需 | 用途 | 传递来源 |
|---------|------|------|------|----------|
| onAddToFeatured | Function | 否 | 加精回调 | Dashboard |
| spiders | Array | 是 | 爬虫列表 | Dashboard |

---

## Tab 2: 归档池 (ArchiveTab)
...
```

**方法 2：让 AI 生成测试脚本**

```
"请基于 Dashboard.jsx 生成一份人工测试脚本。

格式：
## 测试脚本：数据管理Tab

### 测试用例 1：加精功能
**步骤**：
1. 打开数据管理Tab
2. 点击任意一行的"加精"按钮
3. 切换到"新闻输出"Tab

**预期结果**：
- 弹出"加精成功"提示
- 新闻输出Tab的"手动加精"列表中出现该新闻

**验证代码位置**：
- 按钮定义：Dashboard.jsx L156
- 处理函数：Dashboard.jsx L89-96

将结果保存为 TEST_SCRIPT.md"
```

**使用清单的工作流**：
```
重构前:
1. AI 生成 FEATURE_INVENTORY.md
2. AI 生成 TEST_SCRIPT.md  
3. 你审核清单，确认完整性
4. Git commit 保存

重构中:
5. 按 FEATURE_INVENTORY.md 逐项重构
6. 每完成一项在清单中打勾
7. Git commit

重构后:
8. 按 TEST_SCRIPT.md 逐项测试
9. 对比前后清单，确认无遗漏
10. 最终 Git commit
```

#### Step 2: Git 备份
```bash
git add .
git commit -m "chore: backup before refactoring"
git branch backup-before-refactor
```

#### Step 3: 制定重构计划
```
"请制定重构计划：
1. 哪些代码可以拆分
2. 拆分的顺序
3. 每个拆分的目标文件
4. 可能的风险点

不要动手，先给我计划审核。"
```

### 重构执行（分步进行）

#### 单个组件重构流程
```
"开始重构第一个组件：[组件名]

要求：
1. 必须保留 FEATURE_INVENTORY.md 中列出的所有功能
2. Props 接口要清晰明确
3. 添加 PropTypes 定义
4. 保持代码风格一致

重构完成后，请列出：
- 创建了哪些新文件
- 修改了哪些文件
- 移动了哪些功能
- 改变了哪些接口"
```

#### 验证检查清单
```
每重构一个组件后：
- [ ] 刷新浏览器，无报错
- [ ] 对照 FEATURE_INVENTORY.md 逐项测试
- [ ] 所有按钮、输入框都正常
- [ ] 数据加载和显示正常
- [ ] Git commit
```

#### 遇到问题处理
```
❌ 不要说：
"有bug，帮我重新写一遍"

✅ 要说：
"重构后发现问题：
1. [具体问题描述]
2. 预期行为：xxx
3. 实际行为：yyy
4. 错误信息：zzz

请修复这个具体问题，不要改动其他部分。"
```

---

## 📝 最佳实践

### 与 AI 沟通技巧

#### 1. 提供充分上下文
```
❌ 不好的问题：
"这个报错怎么办？"

✅ 好的问题：
"在 Dashboard.jsx 第 XX 行，出现错误：
[粘贴完整错误信息]

这个函数的作用是 [说明]，
我期望的是 [描述]，
但实际发生了 [描述]。

请帮我分析原因并给出修复方案。"
```

#### 2. 分阶段沟通
```
阶段 1：需求确认
"我想实现 xxx，你理解的需求是什么？"

阶段 2：方案设计
"请给出实现方案，不要写代码。"

阶段 3：实施
"方案确认，请实现第一步。"

阶段 4：验证
"测试通过，继续下一步。"
```

#### 3. 明确边界
```
✅ 明确告诉 AI：
- 哪些可以改
- 哪些不能动
- 改到什么程度
- 什么时候停下来让你检查
```

### Git 使用规范

#### Commit 频率
```
✅ 好的实践：
- 每完成一个功能点就 commit
- Commit message 清晰描述改动
- 重要节点打 tag

❌ 不好的实践：
- 改了很多才 commit
- Commit message 模糊
- 长时间不 commit
```

#### Commit Message 格式
```
feat: 新功能
fix: 修复bug
refactor: 重构
docs: 文档更新
style: 代码格式
test: 测试
chore: 构建/工具变动

示例：
git commit -m "feat: add user search functionality"
git commit -m "fix: resolve Tag import error in NewsManagementTab"
git commit -m "refactor: extract NewsToolbar component"
```

#### 分支策略
```bash
# 主分支
main/master - 生产环境代码

# 开发分支
dev - 日常开发

# 功能分支
feature/user-management
feature/dashboard-refactor

# 备份分支
backup-before-refactor
backup-YYYYMMDD
```

---

## ⚠️ 常见陷阱

### 陷阱 1: 一次改太多
```
❌ 错误：
"帮我重构整个项目"

✅ 正确：
"我们逐个 Tab 重构，先从最简单的开始"
```

### 陷阱 2: 盲目信任
```
❌ 错误：
AI 说改好了就直接提交

✅ 正确：
每次改动都要自己测试验证
```

### 陷阱 3: 缺少备份
```
❌ 错误：
改了很多才发现要回退，但没有 commit

✅ 正确：
频繁 commit，重要节点建立备份分支
```

### 陷阱 4: 沟通不清
```
❌ 错误：
"帮我优化一下"（AI 不知道往哪个方向优化）

✅ 正确：
"帮我优化性能，减少不必要的 API 请求"
```

---

## 🎓 进阶技巧

### 1. 让 AI 生成测试清单
```
"请根据 [组件名] 的功能，生成人工测试清单。

每个测试用例包括：
- 测试步骤
- 预期结果
- 相关代码位置"
```

### 2. 让 AI 做代码审查
```
"请审查 [文件名]，检查：
1. 是否有重复代码
2. 是否有性能问题
3. 是否有安全隐患
4. 是否符合最佳实践
5. 是否有改进建议"
```

### 3. 让 AI 生成文档
```
"请为 [组件名] 生成组件文档，包括：
1. 功能说明
2. Props 接口
3. 使用示例
4. 注意事项"
```

---

## 📚 必备文档模板

### 项目根目录文档结构
```
project/
├── README.md                      # 项目说明
├── PROJECT_DOCUMENTATION.md       # 详细文档
├── AI_COLLABORATION_RULES.md      # AI 协作规范
├── FEATURE_INVENTORY.md           # 功能清单（重构时）
├── CHANGELOG.md                   # 变更日志
└── .gitignore                     # Git 忽略规则
```

---

## ✅ 检查清单

### 每日开发结束前
- [ ] 所有改动已测试
- [ ] 所有改动已 commit
- [ ] 文档已更新
- [ ] 没有遗留的 TODO

### 每个功能完成后
- [ ] 功能测试通过
- [ ] 错误处理完善
- [ ] 用户体验良好
- [ ] 代码已审查
- [ ] 文档已更新
- [ ] Git commit with clear message

### 重构完成后
- [ ] 所有功能测试通过
- [ ] 对照 FEATURE_INVENTORY.md 检查
- [ ] 性能没有下降
- [ ] 没有新的 warning/error
- [ ] 更新 CHANGELOG.md

---

## 🆘 应急指南

### 问题：改坏了，需要回退
```bash
# 回退到上一次 commit
git reset --hard HEAD~1

# 回退到特定 commit
git reset --hard <commit-id>

# 回退到备份分支
git checkout backup-before-refactor

# 只恢复某个文件
git checkout HEAD~1 -- path/to/file
```

### 问题：功能丢失了
```
1. 查看 FEATURE_INVENTORY.md 找到遗失功能
2. 查看 Git history 找到原来的实现
3. 告诉 AI 具体缺失什么，让它补上
4. 测试验证
```

### 问题：出现大量报错
```
1. 不要慌，先看第一个错误
2. 复制完整错误信息给 AI
3. 让 AI 逐个修复
4. 如果改不好，考虑回退
```

---

## 🎯 成功标准

一个好的 Vibe Coding 项目应该：
- ✅ 代码模块化，易于维护
- ✅ 文档完整，新人能快速上手
- ✅ Git history 清晰，易于追溯
- ✅ 所有功能都有测试验证
- ✅ AI 和人类的分工明确

记住：**你是架构师和质量把关者，AI 是执行者和助手。**

---

## 📖 延伸阅读

- Git 最佳实践
- 代码审查清单
- 组件设计模式
- TypeScript 渐进式迁移指南

---

最后更新：基于 Glean 项目实战经验（2024-12-26）
