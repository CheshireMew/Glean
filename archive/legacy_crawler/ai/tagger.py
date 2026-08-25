"""AI标签生成器"""
import openai
import yaml
import json
from typing import Dict, List
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

class AITagger:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'ai_prompts.yaml'
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 初始化DeepSeek客户端
        self.client = openai.OpenAI(
            api_key=os.getenv('DEEPSEEK_API_KEY'),
            base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        )
        
        self.model = 'deepseek-chat'
        self.prompt_template = self.config['tag_generation_prompt']
    
    def generate_tags(self, news_item: Dict) -> Dict:
        """
        为新闻生成标签和评分
        
        返回: {
            'tags': ['标签1', '标签2'],
            'category': '市场',
            'score': 85,
            'summary': '一句话总结'
        }
        """
        title = news_item.get('title', '')
        content = news_item.get('content', '')
        source = news_item.get('source_site', '')
        
        # 构建提示词
        prompt = self.prompt_template.format(
            title=title,
            content=content,
            source=source
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的新闻分析专家，擅长提取关键信息并打标签。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # 较低温度保证稳定性
                max_tokens=300
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 解析JSON结果
            # 移除可能的markdown代码块标记
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            
            # 验证结果格式
            if not all(k in result for k in ['tags', 'category', 'score', 'summary']):
                raise ValueError("AI返回格式不完整")
            
            # 确保tags是列表
            if isinstance(result['tags'], str):
                result['tags'] = [result['tags']]
            
            # 确保score在0-100范围内
            result['score'] = max(0, min(100, float(result['score'])))
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"解析AI返回JSON失败: {e}")
            print(f"原始返回: {result_text}")
            # 返回默认值
            return {
                'tags': ['未分类'],
                'category': '其他',
                'score': 50,
                'summary': title[:30] if len(title) > 30 else title
            }
        
        except Exception as e:
            print(f"AI标签生成失败: {e}")
            return {
                'tags': ['未分类'],
                'category': '其他',
                'score': 50,
                'summary': title[:30] if len(title) > 30 else title
            }
    
    def batch_generate_tags(self, news_list: List[Dict]) -> List[Dict]:
        """批量生成标签"""
        results = []
        for news in news_list:
            result = self.generate_tags(news)
            results.append(result)
        return results


# 测试代码
if __name__ == '__main__':
    tagger = AITagger()
    
    test_news = {
        'title': 'SEC批准首批比特币现货ETF，贝莱德、富达等11家机构获批',
        'content': '美国证券交易委员会(SEC)今日正式批准了11家机构的比特币现货ETF申请，包括贝莱德、富达、灰度等知名资管公司。这是加密货币行业的里程碑事件。',
        'source_site': 'techflow'
    }
    
    print("=== AI标签生成测试 ===\n")
    print(f"标题: {test_news['title']}\n")
    
    result = tagger.generate_tags(test_news)
    
    print(f"标签: {', '.join(result['tags'])}")
    print(f"分类: {result['category']}")
    print(f"评分: {result['score']}/100")
    print(f"总结: {result['summary']}")
