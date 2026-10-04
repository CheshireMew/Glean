import hashlib
import hmac
from .config import settings
from .exceptions import APIException


def cookie_name():
    return '__Host-glean_session' if settings.ENV == 'production' else 'glean_session'


def csrf_token(token, secret):
    return hmac.new(secret.encode(), ('csrf:' + token).encode(), hashlib.sha256).hexdigest()


def require_csrf(request, token, secret):
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        supplied = request.headers.get('X-CSRF-Token', '')
        if not hmac.compare_digest(supplied, csrf_token(token, secret)):
            raise APIException('请求验证失效，请重新加载页面', code=403)


def set_session_cookie(response, token):
    response.set_cookie(cookie_name(), token, max_age=12 * 3600, httponly=True,
                        secure=settings.ENV == 'production', samesite='strict', path='/')


def clear_session_cookie(response):
    response.delete_cookie(cookie_name(), httponly=True, secure=settings.ENV == 'production',
                           samesite='strict', path='/')
