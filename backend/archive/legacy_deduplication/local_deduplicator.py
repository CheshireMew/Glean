"""本地去重模块 - 极简版本"""
import re
import json
import os
from typing import List, Tuple
from difflib import SequenceMatcher
from datetime import datetime
import logging

try:
    import jieba
    jieba.setLogLevel(logging.ERROR)
    
    # 加密货币常用词
    crypto_terms = [
        # 交易所
        '币安', 'Binance', 'Coinbase', 'OKX', 'Bybit', 'Kraken', 'Bitfinex',
        # 人物
        'CZ', '赵长鹏', 'SBF', 'Vitalik',
        # DeFi项目
        'Aave', 'Uniswap', 'Curve', 'Compound', 'MakerDAO', 'Lido',
        # Layer2
        'Arbitrum', 'Optimism', 'Base', 'zkSync', 'StarkNet',
        # 其他项目
        'Polymarket', 'OpenSea', 'Blur', 'Sonic', 'Hyperliquid',
        # 公链
        'Solana', 'Avalanche', 'Polygon', 'Fantom', 'Cosmos',
        # 稳定币
        'USDT', 'USDC', 'DAI', 'BUSD',
        # 概念
        'DeFi', 'NFT', 'DAO', 'Web3', 'GameFi', 'SocialFi'
    ]
    
    for term in crypto_terms:
        jieba.add_word(term)
except ImportError:
    jieba = None

class LocalDeduplicator:
    """
    本地新闻去重器（极简版）
    
    核心逻辑：
    1. 分词提取关键词
    2. 计算序列相似度和关键词相似度
    3. 简单清晰，没有复杂的数字处理
    """
    
    def __init__(self, similarity_threshold: float = 0.50, time_window_hours: int = 24):
        """
        Args:
            similarity_threshold: 相似度阈值 (0-1)，默认0.50
            time_window_hours: 时间窗口（小时），默认24
        """
        self.similarity_threshold = similarity_threshold
        self.time_window_hours = time_window_hours
        
        # 加载同义词字典（可选）
        self.synonyms = {}
        try:
            json_path = os.path.join(os.path.dirname(__file__), 'synonyms.json')
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.synonyms = json.load(f)
        except Exception:
            pass
        
        # 将同义词添加到jieba词典
        if jieba and self.synonyms:
            for k, v in self.synonyms.items():
                if len(k) > 1:
                    jieba.add_word(k)
                if v and len(v) > 1:
                    jieba.add_word(v)
    
    def extract_features(self, title: str) -> dict:
        """
        提取标题特征
        
        Returns:
            {
                'keywords': set,      # 关键词集合
                'normalized': str     # 标准化文本
            }
        """
        # 同义词替换
        text = title
        for k, v in self.synonyms.items():
            if k.isascii():
                text = re.sub(re.escape(k), v, text, flags=re.IGNORECASE)
            else:
                text = text.replace(k, v)
        
        # 中文数字单位转换（转换为标准数字）
        # 支持：万、千、亿、k、m、b
        def normalize_number_units(text):
            """将带中文单位的数字转换为标准数字"""
            # 中文单位
            text = re.sub(r'(\d+\.?\d*)\s*万', lambda m: str(float(m.group(1)) * 10000), text)
            text = re.sub(r'(\d+\.?\d*)\s*千', lambda m: str(float(m.group(1)) * 1000), text)
            text = re.sub(r'(\d+\.?\d*)\s*亿', lambda m: str(float(m.group(1)) * 100000000), text)
            # 英文单位（不区分大小写）
            text = re.sub(r'(\d+\.?\d*)\s*[kK]', lambda m: str(float(m.group(1)) * 1000), text, flags=re.IGNORECASE)
            text = re.sub(r'(\d+\.?\d*)\s*[mM]', lambda m: str(float(m.group(1)) * 1000000), text, flags=re.IGNORECASE)
            text = re.sub(r'(\d+\.?\d*)\s*[bB]', lambda m: str(float(m.group(1)) * 1000000000), text, flags=re.IGNORECASE)
            return text
        
        text = normalize_number_units(text)
        
        # 基础停用词
        stop_words = {
            # 中文停用词
            '的', '了', '在', '和', '与', '及', '等', '把', '给', '让', '从', '到', '处', '于',
            # 英文停用词
            'is', 'are', 'to', 'for', 'in', 'on', 'at', 'with', 'by', 'of', 'and', 'or',
            # 通用词
            '枚', '万枚', '个'
        }
        
        # 币种停用词（仅在价格新闻中启用）
        crypto_stop_words = {
            'BTC', 'ETH', 'USDT', 'USDC', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'TRX',
            'btc', 'eth', 'usdt', 'usdc', 'bnb', 'sol', 'xrp', 'ada', 'doge', 'trx',
            '比特币', '以太坊','ETF'
        }
        
        # 检测价格新闻：包含"美元"或"USDT"
        is_price_news = '美元' in title or 'USDT' in title or 'usdt' in title
        if is_price_news:
            stop_words.update(crypto_stop_words)
        
        # 分词
        if jieba:
            words = set(jieba.cut_for_search(text))
        else:
            # 简单后备方案
            words = set(re.findall(r'[A-Za-z]+|\d+|[\u4e00-\u9fa5]+', text))
        
        # 分离英文、中文关键词和数字
        en_keywords = set()
        zh_keywords = set()
        numbers = set()
        
        for w in words:
            w = w.strip()
            if len(w) < 2: continue
            if w in stop_words: continue
            
            # 处理数字
            if re.match(r'^\d+(\.\d+)?$', w):
                try:
                    num_val = float(w)
                    if num_val < 10 or 2010 <= num_val <= 2030 or len(w) > 10:
                        continue
                    numbers.add(w)
                except:
                    numbers.add(w)
                continue
            
            # 分离英文和中文
            if re.match(r'^[A-Za-z]+$', w):
                en_keywords.add(w.lower())
            else:
                zh_keywords.add(w)
        
        return {
            'en_keywords': en_keywords,
            'zh_keywords': zh_keywords,
            'numbers': numbers,
            'keywords': en_keywords | zh_keywords,
            'normalized': re.sub(r'[^\w\s]', '', text.lower()).replace(' ', '')
        }
    
    def calculate_similarity(self, features1: dict, features2: dict) -> float:
        """动态权重分配相似度计算"""
        
        # 计算各维度相似度
        seq_sim = SequenceMatcher(None, features1['normalized'], features2['normalized']).ratio()
        
        en1 = features1.get('en_keywords', set())
        en2 = features2.get('en_keywords', set())
        has_en = bool(en1 or en2)
        en_sim = len(en1 & en2) / len(en1 | en2) if en1 and en2 else 0.0
        
        zh1 = features1.get('zh_keywords', set())
        zh2 = features2.get('zh_keywords', set())
        has_zh = bool(zh1 or zh2)
        zh_sim = len(zh1 & zh2) / len(zh1 | zh2) if zh1 and zh2 else 0.0
        
        nums1 = [float(n) for n in features1.get('numbers', set())]
        nums2 = [float(n) for n in features2.get('numbers', set())]
        has_num = bool(nums1 or nums2)
        
        if nums1 and nums2:
            matched = 0
            for n1 in nums1:
                for n2 in nums2:
                    if n1 == 0 and n2 == 0:
                        matched += 1
                        break
                    elif n1 == 0 or n2 == 0:
                        if abs(n1 - n2) < 10:
                            matched += 1
                            break
                    else:
                        if abs(n1 - n2) / max(n1, n2) < 0.2:
                            matched += 1
                            break
            num_sim = matched / max(len(nums1), len(nums2))
        else:
            num_sim = 0.0
        
        # 动态权重分配
        # 基础权重：序列30%、英文20%、中文20%、数字30%
        base_weights = {'seq': 0.30, 'en': 0.20, 'zh': 0.20, 'num': 0.30}
        active_weights = {'seq': base_weights['seq']}
        
        # 智能分配关键词权重
        if has_en and has_zh:
            # 都有：保持原权重
            active_weights['en'] = base_weights['en']
            active_weights['zh'] = base_weights['zh']
        elif has_en and not has_zh:
            # 只有英文：英文得到全部关键词权重
            active_weights['en'] = base_weights['en'] + base_weights['zh']
        elif not has_en and has_zh:
            # 只有中文：中文得到全部关键词权重
            active_weights['zh'] = base_weights['en'] + base_weights['zh']
        # 都没有：不添加关键词权重
        
        # 数字权重
        if has_num:
            active_weights['num'] = base_weights['num']
        
        # 归一化（缺失权重按比例分给其他特征）
        total = sum(active_weights.values())
        norm_weights = {k: v / total for k, v in active_weights.items()}
        
        # 加权求和
        return (seq_sim * norm_weights.get('seq', 0) +
                en_sim * norm_weights.get('en', 0) +
                zh_sim * norm_weights.get('zh', 0) +
                num_sim * norm_weights.get('num', 0))
    
    def find_duplicates(self, news_list: List[dict]) -> List[Tuple[int, int, float]]:
        """
        找出所有重复对
        Returns: [(index1, index2, similarity), ...] index1 < index2
        """
        if len(news_list) < 2:
            return []

        duplicates = []
        n = len(news_list)
        
        # 预计算特征
        features_list = [self.extract_features(news['title']) for news in news_list]
        
        # 解析时间
        parsed_times = []
        for news in news_list:
            t = news.get('published_at')
            if isinstance(t, str):
                try:
                    # 尝试处理 ISO 格式和常见的 ' ' 分隔格式
                    t_str = t.replace('Z', '+00:00')
                    
                    # 补充: 处理 "2025-01-01 10:00:00" 这种中间是空格的情况
                    if 'T' not in t_str and ' ' in t_str:
                        t_str = t_str.replace(' ', 'T')
                        
                    t = datetime.fromisoformat(t_str)
                except:
                    # 获取失败尝试其他格式 (Fallback)
                    try:
                        t = datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
                    except:
                        t = None
            elif not isinstance(t, datetime):
                t = None
            parsed_times.append(t)

        # 两两比较
        total_comparisons = n * (n - 1) // 2
        current = 0
        last_progress = 0
        
        for i in range(n):
            for j in range(i + 1, n):
                current += 1
                
                # 显示进度（每10%输出一次）
                progress = int((current / total_comparisons) * 100)
                if progress >= last_progress + 10 or current == total_comparisons:
                    print(f"  进度: {progress}% ({current}/{total_comparisons}) - 已找到 {len(duplicates)} 对重复", flush=True)
                    last_progress = progress
                
                # 检查时间窗口（固定2小时）
                # 注意：数据库中的published_at已经是北京时间
                if self.time_window_hours > 0 and parsed_times[i] and parsed_times[j]:
                    try:
                        diff_hours = abs((parsed_times[i] - parsed_times[j]).total_seconds() / 3600)
                        if diff_hours > self.time_window_hours:
                            continue  # 超过时间窗口，跳过对比
                    except:
                        pass
                
                # 计算相似度
                sim = self.calculate_similarity(features_list[i], features_list[j])
                
                if sim >= self.similarity_threshold:
                    duplicates.append((i, j, sim))
        
        return duplicates
    
    def mark_duplicates(self, news_list: List[dict]) -> List[dict]:
        """
        标记重复新闻 - 支持Master合并
        
        策略：
        - 按发布时间排序（最新在前）
        - 使用 Union-Find 结构合并相似新闻
        - 所有相似的新闻都指向最旧的那个 master
        """
        if not news_list:
            return news_list
        
        # 按时间倒序排序（最新在前）
        try:
            news_list.sort(key=lambda x: x.get('published_at', ''), reverse=True)
        except:
            pass
        
        # 初始化
        for news in news_list:
            news['is_local_duplicate'] = False
            news['duplicate_of'] = None
        
        # 找重复对
        duplicates = self.find_duplicates(news_list)
        
        if not duplicates:
            return news_list
        
        # 使用字典记录 duplicate 关系：news_id -> master_id
        duplicate_map = {}
        
        # 辅助函数：找到最终的 master（带路径压缩）
        def get_final_master(news_id):
            """递归查找最终的 master，并进行路径压缩"""
            if news_id not in duplicate_map:
                return news_id
            
            # 路径压缩：直接指向最终 master
            final = get_final_master(duplicate_map[news_id])
            duplicate_map[news_id] = final
            return final
        
        # 处理重复对，合并到最旧的 master
        for i, j, sim in duplicates:
            id_i = news_list[i]['id']
            id_j = news_list[j]['id']
            
            # 找到 i 和 j 的最终 master
            master_i = get_final_master(id_i)
            master_j = get_final_master(id_j)
            
            # 如果已经指向同一个 master，跳过
            if master_i == master_j:
                continue
            
            # 合并到更旧的 master（索引更大的）
            # i < j 表示 i 更新，j 更旧
            # 所以让较新的 master 指向较旧的 master
            
            # 找到两个 master 的索引
            idx_i = next((idx for idx, n in enumerate(news_list) if n['id'] == master_i), -1)
            idx_j = next((idx for idx, n in enumerate(news_list) if n['id'] == master_j), -1)
            
            if idx_i < idx_j:
                # master_j 更旧，让 master_i 指向 master_j
                duplicate_map[master_i] = master_j
            else:
                # master_i 更旧，让 master_j 指向 master_i
                duplicate_map[master_j] = master_i
        
        # 应用到 news_list
        for news in news_list:
            final_master = get_final_master(news['id'])
            if final_master != news['id']:
                news['is_local_duplicate'] = True
                news['duplicate_of'] = final_master
                news['duplicate_reason'] = f"本地去重：与ID={final_master}相似"
        
        return news_list
    
    def get_dedup_stats(self, news_list: List[dict]) -> dict:
        """获取去重统计"""
        total = len(news_list)
        duplicates = sum(1 for n in news_list if n.get('is_local_duplicate', False))
        unique = total - duplicates
        
        return {
            'total': total,
            'unique': unique,
            'duplicates': duplicates,
            'dedup_rate': f"{duplicates/total*100:.1f}%" if total > 0 else "0%"
        }


if __name__ == '__main__':
    # 简单测试
    dedup = LocalDeduplicator()
    test_cases = [
        {"id": 1, "title": "比特币突破5万美元", "published_at": "2025-01-01T10:00:00Z"},
        {"id": 2, "title": "BTC达到50000美元", "published_at": "2025-01-01T09:00:00Z"},
        {"id": 3, "title": "以太坊新高", "published_at": "2025-01-01T08:00:00Z"}
    ]
    
    result = dedup.mark_duplicates(test_cases)
    for r in result:
        print(f"ID {r['id']}: 是否重复={r['is_local_duplicate']}, 重复自={r['duplicate_of']}")
