def wechat_runtime_name(source_id: int) -> str:
    return f'wechat__{source_id}'


def wechat_source_name(name: str) -> str:
    # Keep names distinct from existing website feeds (e.g. 量子位).
    return f'公众号：{name}'
