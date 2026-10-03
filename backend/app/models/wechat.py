from pydantic import BaseModel, Field


class WechatSourceRequest(BaseModel):
    fake_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    alias: str = Field(default='', max_length=120)
    introduction: str = Field(default='', max_length=2000)


class WechatSourceSettings(BaseModel):
    enabled: bool = True
    default_limit: int = Field(default=10, ge=1, le=100)
    default_interval: int = Field(default=240, ge=30, le=10080)
