# Contributing to AINews

感谢你考虑为 AINews 做出贡献！我们欢迎任何形式的贡献，包括但不限于：

- 🐛 报告Bug
- 💡 提出新功能建议
-  📝 改进文档
- 🔧 提交代码修复或新功能
- 🌐 添加新的爬虫支持

## 📋 行为准则

请确保在参与本项目时保持友好和尊重的态度。我们致力于营造一个开放和包容的社区环境。

## 🐛 报告Bug

如果你发现了Bug，请遵循以下步骤：

1. **检查现有 Issues**: 在当前代码托管页面搜索已有问题，避免重复；这份源码快照不内置或假定某个远程仓库地址
2. **使用Issue模板**: 创建新Issue时，请提供以下信息：
   - Bug的详细描述
   - 复现步骤
   - 预期行为 vs 实际行为
   - 环境信息（操作系统、Python版本、Node版本等）
   - 相关日志或截图

### Bug报告示例

```markdown
**描述**
简洁描述Bug是什么

**复现步骤**
1. 启动后端 `python backend/main.py`
2. 在前端或接口中触发对应操作
3. 观察到错误...

**预期行为**
应该正常抓取新闻...

**实际行为**
出现错误: xxx

**环境**
- OS: Windows 11
- Python: 3.10.5
- Node: 22.x
```

## 💡 功能建议

我们欢迎新功能建议！请通过Issue描述你的想法：

1. **功能的使用场景**: 为什么需要这个功能？
2. **预期实现方式**: 你希望它如何工作？
3. **替代方案**: 是否有其他解决方法？

## 🔧 提交代码

### 开发环境设置

```powershell
# 从维护者提供的真实代码来源取得项目后进入目录
Set-Location E:\Code\AINEWS

python -m pip install -r requirements-dev.lock
python -m playwright install chromium
Set-Location frontend
npm ci
Set-Location ..
```

### 开发流程

1. **创建分支**
   ```powershell
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/bug-description
   ```

2. **编写代码**
   - 遵循项目的代码规范（见下方）
   - 添加必要的注释
   - 如果修改了API，请更新文档

3. **测试你的修改**
   ```powershell
   # 后端回归
   python -m compileall -q backend
   python -m ruff check backend shared --select F --exclude backend/archive
   python -m unittest discover -s backend/tests -v

   # 前端静态检查、测试与不落盘构建
   cd frontend
   npm run lint
   npm test
   node --input-type=module -e "import { build } from 'vite'; await build({ build: { write: false } });"
   ```

4. **提交更改**
   ```powershell
   git add .
   git commit -m "feat: 添加XXX功能" 
   # 或
   git commit -m "fix: 修复XXX问题"
   ```

5. **推送到你的Fork**
   ```powershell
   git push origin feature/your-feature-name
   ```

6. **创建Pull Request**
   - 在实际代码托管平台上向维护分支创建 PR
   - 在PR描述中清楚说明你的修改
   - 链接相关的Issue（如果有）

### Commit Message规范

我们建议使用语义化的commit message：

- `feat: 添加新功能`
- `fix: 修复Bug`
- `docs: 更新文档`
- `style: 代码格式调整（不影响功能）`
- `refactor: 代码重构`
- `test: 添加测试`
- `chore: 构建/工具相关的更改`

**示例**:
```
feat: 添加Binance爬虫支持

- 实现Binance新闻页面的爬取逻辑
- 添加内容清理和时间解析
- 更新文档说明

Closes #123
```

## 📝 代码规范

### Python代码规范（爬虫/后端）

- 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 风格指南
- 使用有意义的变量名和函数名
- 添加类型提示（Type Hints）
- 为复杂逻辑添加注释
- 模块开头添加docstring说明

**示例**:
```python
from typing import List, Dict

class NewsScraper:
    \"\"\"新闻爬虫基类\"\"\"
    
    def fetch_news(self, limit: int = 10) -> List[Dict]:
        \"\"\"抓取新闻列表
        
        Args:
            limit: 最多抓取的新闻数量
            
        Returns:
            新闻字典列表，包含title、url、published_at等字段
        \"\"\"
        pass
```

### JavaScript/React代码规范（前端）

- 使用函数式组件和Hooks
- 变量和函数名使用camelCase
- 组件名使用PascalCase
- 为Props添加PropTypes验证
- 提取可复用的组件和逻辑

**示例**:
```javascript
import PropTypes from 'prop-types';

const NewsCard = ({ title, url, publishedAt }) => {
    // ...implementation
};

NewsCard.propTypes = {
    title: PropTypes.string.isRequired,
    url: PropTypes.string.isRequired,
    publishedAt: PropTypes.string
};

export default NewsCard;
```

### 数据库操作规范

- 所有数据库操作应在 `backend/app/infrastructure/sqlite/` 和 `backend/app/infrastructure/repository_impl/` 中实现
- 使用参数化查询，避免SQL注入
- 为事务性操作添加错误处理
- 记录重要操作的日志

## 🕷️ 添加新爬虫

如果你想为新的新闻网站添加爬虫支撑，请遵循以下步骤：

1. **继承BaseScraper类**
   ```python
   # backend/app/infrastructure/scraper_impl/your_site.py
   from .base import BaseScraper
   
   class YourSiteScraper(BaseScraper):
       def __init__(self):
           super().__init__(
               site_name="yoursite",
               base_url="https://example.com"
           )
       
       async def scrape_important_news(self):
           # 实现抓取逻辑
           pass
   ```

2. **选择传输并注册采集器**
   静态页面、RSS、JSON API 和动态页面分别声明 `http`、`rss`、`api` 或 `browser`，然后在 `backend/app/infrastructure/scrapers.py` 中注册。

3. **测试爬虫**
   ```bash
   python -m backend.worker
   # 同时启动 API 和前端，再通过后台“爬虫控制”触发新的采集器
   ```

4. **更新文档**
   - 在README.md中添加支持的网站说明
   - 如果有特殊配置，更新配置文档

## ❓ 获取帮助

如果你在开发过程中遇到问题：

1. **查看文档**:
   - [README.md](README.md) - 项目概览
   - [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md) - 详细文档
   - [VIBE_CODING_GUIDE.md](VIBE_CODING_GUIDE.md) - 编码指南

2. **搜索Issues**: 可能已有人遇到过同样的问题

3. **提问**: 在Issue中提问，我们会尽快回复

## 📄 许可证

通过贡献代码，你同意你的贡献将遵循本项目的 GNU AGPL v3 或更高版本许可证。

---

再次感谢你的贡献！🎉
