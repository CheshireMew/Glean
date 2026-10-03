from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from ..core.exceptions import AuthenticationError
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.operations import CredentialsUpdateRequest
from ..models.responses import AuthSessionData, TokenData
from ..composition import app_services
from ..services.auth_service import AuthService

router = APIRouter(responses={400: {"model": ErrorEnvelope}, 401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def get_auth_service():
    return app_services.auth()


def get_current_user(token: str = Depends(oauth2_scheme), auth_service: AuthService = Depends(get_auth_service)):
    username = auth_service.verify_token(token)
    if username is None:
        raise AuthenticationError(
            "登录状态已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


@router.post("/login", response_model=APIEnvelope[TokenData])
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    access_token = app_services.credentials.login(
        form_data.username, form_data.password, request.client.host if request.client else "unknown"
    )
    response.headers["Cache-Control"] = "no-store"
    return APIResponse.success(data={"access_token": access_token, "token_type": "bearer"}, message="登录成功")


@router.post("/system/credentials", response_model=APIEnvelope[None])
def update_credentials(req: CredentialsUpdateRequest, request: Request, user: str = Depends(get_current_user)):
    result = app_services.credentials.update_credentials(
        user, req.current_password, req.new_username, req.new_password,
        request.client.host if request.client else "unknown",
    )
    return APIResponse.success(message=result["message"])


@router.post("/logout", response_model=APIEnvelope[None])
def logout(token: str = Depends(oauth2_scheme), user: str = Depends(get_current_user),
           auth_service: AuthService = Depends(get_auth_service)):
    auth_service.revoke_token(token)
    return APIResponse.success(message="已退出登录")


@router.get("/session", response_model=APIEnvelope[AuthSessionData])
def session(response: Response, user: str = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return APIResponse.success(data={"username": user})
