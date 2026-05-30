from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .auth import decode_token
from ..models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if not payload:
        raise credentials_exception
    user_id: int = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    # ADMIN y TECNICO comparten privilegios de administración.
    # TECNICO adicionalmente accede a los logs de debugging.
    if current_user.role not in (UserRole.ADMIN, UserRole.TECNICO):
        raise HTTPException(status_code=403, detail="Se requiere rol de administrador")
    return current_user


def require_tecnico(current_user: User = Depends(get_current_user)) -> User:
    """Para endpoints de logs/debug — solo TECNICO y ADMIN."""
    if current_user.role not in (UserRole.ADMIN, UserRole.TECNICO):
        raise HTTPException(status_code=403, detail="Se requiere rol técnico o administrador")
    return current_user
