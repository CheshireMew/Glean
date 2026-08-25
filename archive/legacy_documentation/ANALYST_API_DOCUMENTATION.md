# 分析师API使用文档

## 概述

AINEWS分析师API允许授权用户通过HTTP请求获取AI筛选的高质量加密货币新闻数据。该API专为二次分析、AI投资建议生成等场景设计。

**基础URL**: `https://你的域名或服务器IP/api/analyst/news`

---

## 认证

所有API请求都需要提供有效的API密钥。

### 获取API密钥

联系项目管理员获取您的专属API密钥。管理员可以在"API配置"界面设置 `analyst_api_key`。

### 如何使用密钥

在请求中添加 `api_key` 参数：

```
GET /api/analyst/news?api_key=你的密钥&hours=24
```

---

## API端点

### GET /api/analyst/news

获取AI筛选的新闻数据。

#### 请求参数

| 参数 | 类型 | 必需 | 默认值 | 范围 | 说明 |
|------|------|------|--------|------|------|
| `api_key` | string | ✅ | - | - | API密钥 |
| `hours` | integer | ❌ | 24 | 1-168 | 时间范围（小时） |
| `min_score` | integer | ❌ | 6 | 1-10 | 最低AI评分 |
| `limit` | integer | ❌ | 50 | 1-100 | 返回数量限制 |

#### 响应格式

**成功响应 (200 OK)**:

```json
{
  "success": true,
  "message": "成功获取 10 条新闻",
  "data": {
    "news": [
      {
        "id": 123,
        "title": "比特币突破10万美元创历史新高",
        "content": "据多家交易所数据显示，比特币价格今日...",
        "source_url": "https://www.theblockbeats.info/flash/325934",
        "source_site": "blockbeats",
        "published_at": "2025-12-27 10:30:00",
        "ai_score": 8.5,
        "ai_summary": "重大市场事件：比特币价格突破心理关口"
      }
    ],
    "metadata": {
      "count": 10,
      "time_range_hours": 24,
      "min_score": 6,
      "query_time": "2025-12-27 11:00:00"
    }
  }
}
```

**错误响应 (401 Unauthorized)**:

```json
{
  "success": false,
  "message": "无效的API密钥。请检查api_key参数或联系管理员获取有效密钥。"
}
```

---

## 使用示例

### Python

#### 基础调用

```python
import requests

# 配置
API_URL = "https://你的域名/api/analyst/news"
API_KEY = "your_api_key_here"

# 发起请求
response = requests.get(API_URL, params={
    "api_key": API_KEY,
    "hours": 24,
    "min_score": 7,
    "limit": 20
})

# 处理响应
if response.status_code == 200:
    data = response.json()
    news_list = data['data']['news']

    for news in news_list:
        print(f"标题: {news['title']}")
        print(f"来源: {news['source_site']}")
        print(f"评分: {news['ai_score']}")
        print(f"链接: {news['source_url']}")
        print(f"内容: {news['content'][:100]}...")
        print("-" * 50)
else:
    print(f"请求失败: {response.status_code}")
    print(response.text)
```

#### 使用AI进行分析

```python
import requests
from openai import OpenAI
import os

# 1. 获取新闻数据
response = requests.get("https://你的域名/api/analyst/news", params={
    "api_key": "your_api_key",
    "hours": 12,
    "min_score": 8
})

news_list = response.json()['data']['news']

# 2. 汇总新闻
news_summary = "\n\n".join([
    f"标题: {n['title']}\n内容: {n['content'][:200]}..."
    for n in news_list
])

# 3. 调用AI生成分析
client = OpenAI(
    api_key=os.environ["AI_API_KEY"],
    base_url=os.environ["AI_BASE_URL"]
)

response = client.chat.completions.create(
    model=os.environ["AI_MODEL"],
    messages=[
        {
            "role": "system",
            "content": "你是一位专业的加密货币市场分析师，请基于提供的新闻给出投资建议。"
        },
        {
            "role": "user",
            "content": f"以下是最近的重要新闻：\n\n{news_summary}\n\n请分析这些新闻对加密市场的影响，并给出交易建议。"
        }
    ]
)

print(response.choices[0].message.content)
```

### JavaScript / Node.js

```javascript
const axios = require('axios');

const API_URL = 'https://你的域名/api/analyst/news';
const API_KEY = 'your_api_key_here';

async function getNews() {
  try {
    const response = await axios.get(API_URL, {
      params: {
        api_key: API_KEY,
        hours: 24,
        min_score: 7,
        limit: 30
      }
    });

    const newsList = response.data.data.news;

    newsList.forEach(news => {
      console.log('标题:', news.title);
      console.log('评分:', news.ai_score);
      console.log('来源:', news.source_site);
      console.log('---');
    });
  } catch (error) {
    console.error('请求失败:', error.response?.data || error.message);
  }
}

getNews();
```

### cURL

```bash
# 基础请求
curl "https://你的域名/api/analyst/news?api_key=your_key&hours=24&min_score=7"

# 格式化输出
curl "https://你的域名/api/analyst/news?api_key=your_key&hours=24" | jq .
```

---

## 数据字段说明

### 新闻对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | integer | 新闻唯一标识 |
| `title` | string | 新闻标题 |
| `content` | string | 新闻完整内容 |
| `source_url` | string | 原文链接 |
| `source_site` | string | 来源网站（blockbeats, odaily, chaincatcher等） |
| `published_at` | string | 发布时间（北京时间，格式：YYYY-MM-DD HH:MM:SS） |
| `ai_score` | float | AI评分（1-10分，分数越高越重要） |
| `ai_summary` | string | AI生成的摘要（可能为空） |

### 元数据对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `count` | integer | 返回的新闻数量 |
| `time_range_hours` | integer | 实际查询的时间范围 |
| `min_score` | integer | 实际使用的最低评分 |
| `query_time` | string | 查询时间 |

---

## 最佳实践

### 1. 合理设置参数

- **短期分析**：`hours=6-12, min_score=8` - 获取最新的高质量新闻
- **日度分析**：`hours=24, min_score=7` - 每日市场概览
- **周度回顾**：`hours=168, min_score=6` - 一周重要新闻汇总

### 2. 错误处理

```python
try:
    response = requests.get(API_URL, params=params, timeout=10)
    response.raise_for_status()  # 检查HTTP状态码
    data = response.json()

    if not data.get('success'):
        print(f"API错误: {data.get('message')}")
except requests.exceptions.Timeout:
    print("请求超时，请稍后重试")
except requests.exceptions.RequestException as e:
    print(f"网络错误: {e}")
```

### 3. 缓存机制

建议实现本地缓存，避免频繁请求：

```python
import time
import json

cache = {"data": None, "timestamp": 0}
CACHE_TTL = 300  # 5分钟

def get_news_cached():
    now = time.time()
    if cache["data"] and (now - cache["timestamp"]) < CACHE_TTL:
        return cache["data"]

    # 从API获取
    response = requests.get(API_URL, params={"api_key": API_KEY})
    data = response.json()

    cache["data"] = data
    cache["timestamp"] = now
    return data
```

---

## 使用限制

- **频率限制**: 目前无限制（未来可能添加）
- **数量限制**: 单次最多返回100条新闻
- **时间范围**: 最多查询最近7天（168小时）的新闻

---

## 常见问题

### Q: 如何获取API密钥？
A: 联系项目管理员。管理员在后台"API配置"中设置密钥后会提供给您。

### Q: API密钥可以共享吗？
A: 目前系统使用单一密钥，可以在团队内共享。未来可能支持多用户独立密钥。

### Q: 返回的新闻是否实时？
A: 新闻由定时爬虫抓取并经过AI筛选，通常延迟在数分钟到1小时之间。

### Q: 如何确保数据安全？
A:
1. 使用HTTPS加密传输
2. 妥善保管API密钥，不要公开
3. 生产环境部署时建议配置防火墙和访问控制

### Q: 可以获取历史数据吗？
A: 目前支持最近7天的数据。如需更久远的历史数据，请联系管理员。

---

## 技术支持

如有问题或建议，请联系项目管理员。

**API版本**: v1.0
**最后更新**: 2025-12-27
