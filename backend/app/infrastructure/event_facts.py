"""Deterministic fact checks before title similarity can merge reports."""
from __future__ import annotations

import re


_ACTIONS = re.compile(
    r"完成|宣布|发布|推出|上线|下线|批准|拒绝|收购|融资|获得|获批|获|"
    r"净流入|净流出|流入|流出|突破|跌破|买入|卖出|持仓|遭|被黑|"
    r"上涨|下跌|增长|下降|增加|减少|启动|暂停|取消|开放|关闭|"
    r"发生|遭遇|达成|签署|支持|成为|转账|转移|聘请|任命|辞职|卸任|退出|披露|公布|指出|表示|确认|报告|回应|"
    r"\b(?:announces?|launches?|raises?|acquires?|approves?|rejects?)\b"
)
_LEADING_CONTEXT = re.compile(
    r"^(?:今日|昨日|今天|昨天|本周|上周|近日|消息称|快讯|据悉|报道称|"
    r"\d{4}年|\d{1,2}月|\d{1,2}日|\s)+"
)
_SUBJECT_SUFFIX = re.compile(r"(?:拟|已|将|计划|打算|正式|首次|再次|昨日|今日|已经|宣布|成功|拟将)+$")
_DIRECTIONS = {
    'flow': (r'净?流入|\binflows?\b', r'净?流出|\boutflows?\b'),
    'price_boundary': (r'突破|\bbreaks? above\b', r'跌破|\bbreaks? below\b'),
    'trade': (r'买入|增持|\b(?:buys?|bought)\b', r'卖出|减持|抛售|\b(?:sells?|sold)\b'),
    'approval': (r'批准|获批|\bapprov\w*\b', r'拒绝|否决|\b(?:reject\w*|denied)\b'),
    'change': (r'上涨|增长|增加|上升|\b(?:rise|rising|increases?)\b', r'下跌|下降|减少|降低|\b(?:falls?|declines?|decreases?)\b'),
    'availability': (r'上线|开放|启动|\blaunch\w*\b', r'下线|关闭|暂停|取消|\b(?:shutdown|cancel\w*)\b'),
}
_PLANNED = re.compile(r'拟|将(?=完成|发布|推出|收购|融资|上线|批准|买入|卖出)|计划|打算|考虑|有意|寻求|尝试|\b(?:plans? to|proposes? to|will|may)\b')
_NEGATED = re.compile(r'尚未|未曾|未获|未(?=完成|批准|收购|上线|发布|推出|融资|买入|卖出)|没有|否认|不会|不再|不批准|\b(?:not|never|denies?)\b')
_QUANTITY = re.compile(r'(?<![\d.])\d+(?:\.\d+)?')
_UNIT = re.compile(r'^(美元|美金|人民币|欧元|英镑|港元|日元|元|%|％|枚|个|家|人|笔|倍|版|年|月|日|天|小时|分钟|秒|比特币|以太坊|泰达币|usd\b|usdt\b|usdc\b)')
_METRICS = re.compile(r'融资|投资|估值|价格|净流入|净流出|流入|流出|收入|营收|利润|亏损|市值|规模|参数|持仓|买入|卖出')
_METRIC_NAMES = {'净流入': 'flow', '净流出': 'flow', '流入': 'flow', '流出': 'flow',
                 '买入': 'trade', '卖出': 'trade', '美元': 'usd', '美金': 'usd'}
_CURRENCIES = {'美元': 'usd', '美金': 'usd', '人民币': 'cny', '元': 'cny', '欧元': 'eur',
               '英镑': 'gbp', '港元': 'hkd', '日元': 'jpy', 'usd': 'usd'}
_GENERIC_OBJECT_WORDS = {'a', 'an', 'the', 'new', 'its', 'of', 'in', 'on', 'to', 'for', 'and',
                         'product', 'products', 'model', 'models', 'million', 'billion', 'usd'}


def extract_facts(text: str, named_entities: set[str]) -> dict:
    directions = {}
    for role, (positive, negative) in _DIRECTIONS.items():
        signs = set()
        if re.search(positive, text):
            signs.add('+')
        if re.search(negative, text):
            signs.add('-')
        if signs:
            directions[role] = signs

    subjects = set()
    objects = set()
    leading = _LEADING_CONTEXT.sub('', text)
    action = _ACTIONS.search(leading)
    if action:
        prefix = _SUBJECT_SUFFIX.sub('', leading[:action.start()].strip())
        entities = {entity for entity in named_entities if entity in prefix}
        if entities:
            subjects = entities
        elif prefix and len(prefix) <= 60:
            subjects = {re.sub(r'\s+', '', subject) for subject in re.split(r'[、]|与|和|及', prefix) if subject}
        remainder = leading[action.end():]
        objects = {entity for entity in named_entities if entity in remainder}
        objects.update(word for word in re.findall(r'[a-z][a-z0-9_-]*', remainder)
                       if word not in _GENERIC_OBJECT_WORDS)
        objects.update(re.findall(r'(?:项目|公司|代币|协议)[a-z0-9]+', remainder))

    quantities = {}
    for match in _QUANTITY.finditer(text):
        before = text[:match.start()]
        after = text[match.end():].lstrip()
        unit_match = _UNIT.match(after)
        unit = unit_match.group(1) if unit_match else 'number'
        unit = _CURRENCIES.get(unit, unit)
        metrics = list(_METRICS.finditer(before))
        metric = _METRIC_NAMES.get(metrics[-1].group(), metrics[-1].group()) if metrics else 'amount'
        # Numeric names/model versions are identity facts, not unimportant title decoration.
        if not unit_match and re.search(r'[a-z]+[- ]?$', before):
            metric = re.search(r'([a-z]+)[- ]?$', before).group(1)
            unit = 'version'
        if unit in {'年', '月', '日', '天', '小时', '分钟', '秒', '版'}:
            metric = 'date' if unit in {'年', '月', '日'} else 'duration' if unit != '版' else 'version'
        number = match.group()
        if before.endswith('-') and (len(before) < 2 or not re.match(r'[a-z]', before[-2])):
            number = '-' + number
        quantities.setdefault(f'{metric}:{unit}', set()).add(number)

    return {'subjects': subjects, 'objects': objects, 'entities': named_entities, 'quantities': quantities,
            'directions': directions, 'state': {'planned' if _PLANNED.search(text) else 'actual'},
            'negated': {'yes' if _NEGATED.search(text) else 'no'}, 'invalid': False}


def facts_conflict(left: dict, right: dict) -> bool:
    if left['invalid'] or right['invalid']:
        return True
    for key in ('subjects', 'objects', 'entities'):
        if (left[key] and right[key] and
                not (left[key] <= right[key] or right[key] <= left[key])):
            return True
    for key in ('state', 'negated'):
        if left[key].isdisjoint(right[key]):
            return True
    for role in left['directions'].keys() & right['directions'].keys():
        if left['directions'][role].isdisjoint(right['directions'][role]):
            return True
    for role in left['quantities'].keys() & right['quantities'].keys():
        if left['quantities'][role].isdisjoint(right['quantities'][role]):
            return True
    currency_units = set(_CURRENCIES.values())
    left_currencies = {role.partition(':')[2] for role in left['quantities']} & currency_units
    right_currencies = {role.partition(':')[2] for role in right['quantities']} & currency_units
    if left_currencies and right_currencies and left_currencies.isdisjoint(right_currencies):
        return True
    # A generic monetary amount must also agree with a more explicitly named metric.
    for a, b in ((left, right), (right, left)):
        for role, values in a['quantities'].items():
            if role.startswith('amount:'):
                unit = role.partition(':')[2]
                other_values = {value for name, found in b['quantities'].items()
                                if name.endswith(':' + unit) for value in found}
                if other_values and values.isdisjoint(other_values):
                    return True
    return False


def merge_facts(left: dict, right: dict) -> dict:
    merged = {key: (left[key] & right[key] if left[key] and right[key] else left[key] | right[key])
              for key in ('subjects', 'objects', 'entities', 'state', 'negated')}
    merged['invalid'] = facts_conflict(left, right)
    for key in ('directions', 'quantities'):
        merged[key] = {role: (left[key][role] & right[key][role]
                             if role in left[key] and role in right[key]
                             else left[key].get(role, set()) | right[key].get(role, set()))
                       for role in left[key].keys() | right[key].keys()}
    return merged
