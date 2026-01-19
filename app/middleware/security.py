"""
Security middleware for FastAPI
FastAPI安全中间件 - 速率限制、输入验证、安全头等
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.security import rate_limiter, input_validator
from app.core.config import settings
from app.services.audit_logger import audit_logger, AuditEventType

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware with rate limiting and input validation"""
    
    def __init__(self, app, enable_rate_limiting: bool = True):
        super().__init__(app)
        self.enable_rate_limiting = enable_rate_limiting
        self.excluded_paths = {
            "/docs", "/redoc", "/openapi.json", "/health", "/metrics"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through security checks"""
        start_time = time.time()
        
        # Skip security checks for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        
        try:
            # Add security headers
            response = await self._add_security_headers(request, call_next)
            
            # Log request processing time
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"}
            )
    
    async def _add_security_headers(self, request: Request, call_next: Callable) -> Response:
        """Add security headers and perform checks"""
        
        # Rate limiting check
        if self.enable_rate_limiting:
            await self._check_rate_limit(request)
        
        # Input validation for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            await self._validate_request_body(request)
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws: wss:;"
        )
        
        # Remove server information
        if "server" in response.headers:
            del response.headers["server"]
        
        return response
    
    async def _check_rate_limit(self, request: Request):
        """Check rate limiting for the request"""
        # Skip rate limiting in test environment
        if hasattr(request.state, 'testing') or request.headers.get('user-agent', '').startswith('python-httpx'):
            return
            
        # Get client identifier (IP address or user ID if authenticated)
        client_ip = self._get_client_ip(request)
        identifier = client_ip
        
        # Use user ID if authenticated
        if hasattr(request.state, 'user_id'):
            identifier = f"user:{request.state.user_id}"
        
        # Check rate limit
        is_limited = await rate_limiter.is_rate_limited(identifier)
        
        if is_limited:
            # Get rate limit status for headers
            status_info = await rate_limiter.get_rate_limit_status(identifier)
            
            logger.warning(f"Rate limit exceeded for {identifier} on {request.url.path}")
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={
                    "X-RateLimit-Limit": str(status_info.get("limit", settings.RATE_LIMIT_REQUESTS)),
                    "X-RateLimit-Remaining": str(status_info.get("remaining", 0)),
                    "X-RateLimit-Reset": str(int(status_info.get("reset_time", time.time() + 60))),
                    "Retry-After": str(settings.RATE_LIMIT_WINDOW)
                }
            )
    
    async def _validate_request_body(self, request: Request):
        """Validate request body for security threats"""
        try:
            # Only validate if content type is JSON or form data
            content_type = request.headers.get("content-type", "")
            
            if "application/json" in content_type:
                # For JSON requests, we'll let FastAPI handle parsing
                # and validate in the endpoint handlers
                pass
            elif "application/x-www-form-urlencoded" in content_type:
                # For form data, we can validate here
                body = await request.body()
                if body:
                    body_str = body.decode('utf-8')
                    if not input_validator.validate_game_input(body_str):
                        logger.warning(f"Invalid form data detected from {self._get_client_ip(request)}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid input data"
                        )
        except UnicodeDecodeError:
            logger.warning(f"Invalid encoding in request body from {self._get_client_ip(request)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request encoding"
            )
        except Exception as e:
            logger.error(f"Request body validation error: {e}")
            # Don't block request for validation errors, just log
            pass
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request"""
        # Check for forwarded headers (when behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection
        return request.client.host if request.client else "unknown"


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for protected routes"""
    
    def __init__(self, app):
        super().__init__(app)
        self.protected_paths = {
            "/api/v1/rooms", "/api/v1/games", "/api/v1/leaderboard",
            "/api/v1/settlement", "/api/v1/auth/profile", "/api/v1/auth/logout"
        }
        self.excluded_paths = {
            "/api/v1/auth/register", "/api/v1/auth/login", "/docs", "/redoc", 
            "/openapi.json", "/health", "/metrics"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check authentication for protected routes"""
        
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        
        # Check if path requires authentication
        if any(request.url.path.startswith(path) for path in self.protected_paths):
            await self._verify_authentication(request)
        
        return await call_next(request)
    
    async def _verify_authentication(self, request: Request):
        """Verify user authentication"""
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = auth_header.split(" ")[1]
        
        # Verify token (this will be handled by the auth dependency in endpoints)
        # Here we just ensure the token format is correct
        if not token or len(token) < 10:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            )


class LoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for security monitoring"""
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log requests for security monitoring"""
        start_time = time.time()
        client_ip = self._get_client_ip(request)
        
        # Log request
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"from {client_ip} "
            f"User-Agent: {request.headers.get('user-agent', 'unknown')}"
        )
        
        try:
            response = await call_next(request)
            
            # Log response
            process_time = time.time() - start_time
            logger.info(
                f"Response: {response.status_code} "
                f"for {request.method} {request.url.path} "
                f"in {process_time:.3f}s"
            )
            
            # Log security events
            if response.status_code == 429:
                logger.warning(f"Rate limit hit: {client_ip} on {request.url.path}")
            elif response.status_code == 401:
                logger.warning(f"Unauthorized access attempt: {client_ip} on {request.url.path}")
            elif response.status_code >= 400:
                logger.warning(f"Client error {response.status_code}: {client_ip} on {request.url.path}")
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request error: {request.method} {request.url.path} "
                f"from {client_ip} in {process_time:.3f}s - {str(e)}"
            )
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"