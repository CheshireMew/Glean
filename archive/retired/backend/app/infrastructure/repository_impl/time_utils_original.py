
from datetime import datetime, timezone, timedelta

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))

def get_beijing_time():
    """获取当前北京时间"""
    return datetime.now(BEIJING_TZ)

def format_beijing_time(dt):
    """格式化时间为北京时区字符串"""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    # 确保时间带有时区信息
    if dt.tzinfo is None:
        # 假设输入是北京时间
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        # 转换为北京时间
        dt = dt.astimezone(BEIJING_TZ)
    return dt.strftime('%Y-%m-%d %H:%M:%S')
