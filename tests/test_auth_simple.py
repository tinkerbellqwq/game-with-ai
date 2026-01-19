"""
Simple user authentication tests
简单用户认证测试
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


class TestAuthenticationEndpoints:
    """Test authentication API endpoints with basic functionality"""
    
    @pytest.mark.asyncio
    async def test_auth_endpoints_exist(self, override_get_db):
        """Test that authentication endpoints exist and respond"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test register endpoint exists
            response = await client.post("/api/v1/auth/register", json={
                "username": "test",
                "email": "invalid-email",  # This should fail validation
                "password": "short"  # This should fail validation
            })
            # Should return validation error, not 404
            assert response.status_code in [400, 422]  # Validation error, not not found
            
            # Test login endpoint exists
            response = await client.post("/api/v1/auth/login", json={
                "username": "test",
                "password": "test"
            })
            # Should return auth error, not 404
            assert response.status_code in [401, 422]  # Auth error, not not found
            
            # Test profile endpoint exists (should require auth)
            response = await client.get("/api/v1/auth/profile")
            # Should return auth required, not 404
            assert response.status_code in [401, 403]  # Auth required, not not found
    
    @pytest.mark.asyncio
    async def test_register_validation(self, override_get_db):
        """Test registration input validation"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test invalid email
            response = await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "invalid-email",
                "password": "password123"
            })
            assert response.status_code == 422
            
            # Test short password
            response = await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "short"
            })
            assert response.status_code == 422
            
            # Test short username
            response = await client.post("/api/v1/auth/register", json={
                "username": "ab",
                "email": "test@example.com",
                "password": "password123"
            })
            assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_login_validation(self, override_get_db):
        """Test login input validation"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test missing fields
            response = await client.post("/api/v1/auth/login", json={
                "username": "test"
                # Missing password
            })
            assert response.status_code == 422
            
            # Test empty fields
            response = await client.post("/api/v1/auth/login", json={
                "username": "",
                "password": ""
            })
            assert response.status_code in [401, 422]  # Either validation error or auth error is acceptable
    
    @pytest.mark.asyncio
    async def test_protected_endpoints_require_auth(self, override_get_db):
        """Test that protected endpoints require authentication"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test profile endpoint without auth
            response = await client.get("/api/v1/auth/profile")
            assert response.status_code in [401, 403]
            
            # Test verify endpoint without auth
            response = await client.get("/api/v1/auth/verify")
            assert response.status_code in [401, 403]
            
            # Test logout endpoint without auth
            response = await client.post("/api/v1/auth/logout")
            assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_api_structure(self, override_get_db):
        """Test that the API structure is correct"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test that /api/v1/auth routes exist (not 404)
            endpoints = [
                "/api/v1/auth/register",
                "/api/v1/auth/login",
                "/api/v1/auth/profile",
                "/api/v1/auth/verify",
                "/api/v1/auth/logout"
            ]
            
            for endpoint in endpoints:
                if endpoint in ["/api/v1/auth/register", "/api/v1/auth/login"]:
                    response = await client.post(endpoint, json={})
                else:
                    response = await client.get(endpoint) if "profile" in endpoint or "verify" in endpoint else await client.post(endpoint)
                
                # Should not be 404 (not found) - endpoints should exist
                assert response.status_code != 404, f"Endpoint {endpoint} not found"


class TestTokenValidation:
    """Test JWT token functionality"""
    
    def test_token_creation_and_verification(self):
        """Test JWT token creation and verification"""
        from app.services.auth import auth_service
        
        data = {"sub": "user123", "username": "testuser"}
        token = auth_service.create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        
        payload = auth_service.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        
        # Test invalid token
        invalid_payload = auth_service.verify_token("invalid.token.here")
        assert invalid_payload is None


class TestUserSchemaValidation:
    """Test user schema validation"""
    
    def test_user_create_schema(self):
        """Test UserCreate schema validation"""
        from app.schemas.user import UserCreate
        from pydantic import ValidationError
        
        # Valid user data
        valid_user = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        assert valid_user.username == "testuser"
        assert valid_user.email == "test@example.com"
        assert valid_user.password == "password123"
        
        # Invalid email
        with pytest.raises(ValidationError):
            UserCreate(
                username="testuser",
                email="invalid-email",
                password="password123"
            )
        
        # Short password
        with pytest.raises(ValidationError):
            UserCreate(
                username="testuser",
                email="test@example.com",
                password="short"
            )
        
        # Short username
        with pytest.raises(ValidationError):
            UserCreate(
                username="ab",
                email="test@example.com",
                password="password123"
            )
    
    def test_user_login_schema(self):
        """Test UserLogin schema validation"""
        from app.schemas.user import UserLogin
        from pydantic import ValidationError
        
        # Valid login data
        valid_login = UserLogin(
            username="testuser",
            password="password123"
        )
        assert valid_login.username == "testuser"
        assert valid_login.password == "password123"
        
        # Missing fields should raise validation error
        with pytest.raises(ValidationError):
            UserLogin(username="testuser")  # Missing password
        
        with pytest.raises(ValidationError):
            UserLogin(password="password123")  # Missing username