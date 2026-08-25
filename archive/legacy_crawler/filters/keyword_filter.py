"""关键词过滤器"""
import re
import yaml
from typing import Dict, List, Tuple
from pathlib import Path

class KeywordFilter:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'filters.yaml'
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 编译正则表达式（提升性能）
        self.blacklist_patterns: List[Tuple[re.Pattern, str]] = [
            (re.compile(p['regex']), p['reason']) 
            for p in self.config['blacklist']['patterns']
        ]
        
        self.whitelist_patterns: List[Tuple[re.Pattern, str]] = [
            (re.compile(p['regex']), p['reason']) 
            for p in self.config['whitelist']['patterns']
        ]
        
        self.blacklist_keywords = self.config['blacklist']['keywords']
        self.whitelist_keywords = self.config['whitelist']['keywords']
        
        self.min_length = self.config['length']['min_chars']
        self.max_length = self.config['length']['max_chars']
    
    def filter_news(self, news_item: Dict) -> Dict:
        """
        过滤新闻
        
        返回: {
            'passed': bool,
            'reason': str,
            'matched_whitelist': bool,
            'matched_rule': str  # 用于统计
        }
        """
        title = news_item.get('title', '')
        content = news_item.get('content', '')
        text = f"{title} {content}"
        
        # 1. 长度检查
        if len(text) < self.min_length:
            return {
                'passed': False,
                'reason': f'内容过短（{len(text)}字）',
                'matched_whitelist': False,
                'matched_rule': f'length_min_{self.min_length}'
            }
        
        if len(text) > self.max_length:
            return {
                'passed': False,
                'reason': f'内容过长（{len(text)}字）',
                'matched_whitelist': False,
                'matched_rule': f'length_max_{self.max_length}'
            }
        
        # 2. 白名单优先（强制保留）
        for pattern, reason in self.whitelist_patterns:
            if pattern.search(text):
                return {
                    'passed': True, 
                    'reason': f'白名单命中: {reason}',
                    'matched_whitelist': True,
                    'matched_rule': f'whitelist_regex_{reason}'
                }
        
        # 白名单关键词
        for keyword in self.whitelist_keywords:
            if keyword in text:
                return {
                    'passed': True,
                    'reason': f'白名单关键词: {keyword}',
                    'matched_whitelist': True,
                    'matched_rule': f'whitelist_keyword_{keyword}'
                }
        
        # 3. 黑名单检查
        for pattern, reason in self.blacklist_patterns:
            if pattern.search(text):
                return {
                    'passed': False, 
                    'reason': f'黑名单命中: {reason}',
                    'matched_whitelist': False,
                    'matched_rule': f'blacklist_regex_{reason}'
                }
        
        # 4. 关键词黑名单
        for keyword in self.blacklist_keywords:
            if keyword in text:
                return {
                    'passed': False, 
                    'reason': f'黑名单关键词: {keyword}',
                    'matched_whitelist': False,
                    'matched_rule': f'blacklist_keyword_{keyword}'
                }
        
        # 默认通过
        return {
            'passed': True, 
            'reason': '通过初筛',
            'matched_whitelist': False,
            'matched_rule': 'passed_default'
        }
    
    def get_stats_summary(self):
        """返回配置统计"""
        return {
            'blacklist_patterns': len(self.blacklist_patterns),
            'whitelist_patterns': len(self.whitelist_patterns),
            'blacklist_keywords': len(self.blacklist_keywords),
            'whitelist_keywords': len(self.whitelist_keywords),
            'min_length': self.min_length,
            'max_length': self.max_length
        }


# 测试代码
if __name__ == '__main__':
    filter = KeywordFilter()
    
    # 测试用例
    test_cases = [
        {
            'title': 'BTC 24小时涨幅3.2%，现报42,150美元',
            'content': ''
        },
        {
            'title': 'SEC批准首个比特币现货ETF',
            'content': '美国证券交易委员会今日批准了贝莱德的比特币现货ETF申请'
        },
        {
            'title': 'X平台某KOL发文表示看好以太坊',
            'content': ''
        },
        {
            'title': 'MicroStrategy再次购入10000枚BTC',
            'content': '上市公司MicroStrategy宣布以5亿美元购入1万枚比特币'
        }
    ]
    
    print("=== 关键词过滤测试 ===\n")
    for i, news in enumerate(test_cases, 1):
        result = filter.filter_news(news)
        status = "✅ 通过" if result['passed'] else "❌ 过滤"
        print(f"{i}. {status}")
        print(f"   标题: {news['title']}")
        print(f"   原因: {result['reason']}")
        print()
    
    print("配置统计:", filter.get_stats_summary())
