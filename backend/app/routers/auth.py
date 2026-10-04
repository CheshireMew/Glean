from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordBearer
from urllib.parse import parse_qsl
from ..core.browser_session import cookie_name, csrf_token, require_csrf, set_session_cookie, clear_session_cookie
from ..core.exceptions import APIException
from ..core.exceptions import AuthenticationError
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.operations import CredentialsUpdateRequest
from ..models.responses import AuthSessionData, TokenData
from ..composition import app_services
from ..services.auth_service import AuthService

router = APIRouter(responses={400: {"model": ErrorEnvelope}, 401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


def get_auth_service():
    return app_services.auth()


def get_session_token(request: Request, bearer: str | None = Depends(oauth2_scheme)):
    token = bearer or request.cookies.get(cookie_name())
    if not token:
        raise AuthenticationError("请先登录", headers={"WWW-Authenticate": "Bearer"})
    return token


def get_current_user(request: Request, token: str = Depends(get_session_token),
                     bearer: str | None = Depends(oauth2_scheme),
                     auth_service: AuthService = Depends(get_auth_service)):
    username = auth_service.verify_token(token)
    if username is None:
        raise AuthenticationError(
            "登录状态已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not bearer:
        require_csrf(request, token, auth_service.secret_key)
    return username


async def login_form(request: Request):
    if request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
        raise APIException('登录必须使用表单格式', code=415)
    try:
        fields = parse_qsl((await request.body()).decode('utf-8'), keep_blank_values=True, max_num_fields=6)
    except (ValueError, UnicodeError):
        raise APIException('登录表单无效或字段过多', code=400)
    allowed = {'username', 'password', 'scope', 'grant_type', 'client_id', 'client_secret'}
    values = dict(fields)
    if len(values) != len(fields) or set(values) - allowed or not {'username', 'password'} <= values.keys():
        raise APIException('登录表单字段无效', code=400)
    if len(values['username']) > 64 or len(values['password']) > 256:
        raise APIException('账号或密码长度无效', code=400)
    return values


@router.post("/login", response_model=APIEnvelope[TokenData], response_model_exclude_none=True)
def login(request: Request, response: Response, form_data: dict = Depends(login_form)):
    access_token = app_services.credentials.login(
        form_data['username'], form_data['password'], request.client.host if request.client else "unknown"
    )
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get('X-Glean-Session') == 'browser':
        set_session_cookie(response, access_token)
        data = {'token_type': 'cookie', 'csrf_token': csrf_token(access_token, app_services.auth().secret_key)}
    else:
        data = {"access_token": access_token, "token_type": "bearer"}
    return APIResponse.success(data=data, message="登录成功")


@router.post("/system/credentials", response_model=APIEnvelope[None])
def update_credentials(req: CredentialsUpdateRequest, request: Request, user: str = Depends(get_current_user)):
    result = app_services.credentials.update_credentials(
        user, req.current_password, req.new_username, req.new_password,
        request.client.host if request.client else "unknown",
    )
    return APIResponse.success(message=result["message"])


@router.post("/logout", response_model=APIEnvelope[None])
def logout(response: Response, token: str = Depends(get_session_token), user: str = Depends(get_current_user),
           auth_service: AuthService = Depends(get_auth_service)):
    auth_service.revoke_token(token)
    clear_session_cookie(response)
    return APIResponse.success(message="已退出登录")


@router.get("/session", response_model=APIEnvelope[AuthSessionData])
def session(response: Response, user: str = Depends(get_current_user), token: str = Depends(get_session_token)):
    response.headers["Cache-Control"] = "no-store"
    return APIResponse.success(data={"username": user, "csrf_token": csrf_token(token, app_services.auth().secret_key)})
