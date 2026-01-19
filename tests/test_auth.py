"""
User authentication tests
用户认证测试
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services.auth import auth_service
from app.schemas.user import UserCreate, UserLogin
from app.models.user import User


class TestUserAuthentication:
    """Test user authentication functionality"""
    
    @pytest.mark.asyncio
    async def test_user_registration_success(self, test_session: AsyncSession):
        """Test successful user registration"""
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        
        result = await auth_service.register_user(test_session, user_data)
        
        assert result.username == "testuser"
        assert result.email == "test@example.com"
        assert result.score == 0
        assert result.games_played == 0
        assert result.games_won == 0
        assert result.is_active is True
    
    @pytest.mark.asyncio
    async def test_user_registration_duplicate_username(self, test_session: AsyncSession):
        """Test registration with duplicate username"""
        # Create first user
        user_data1 = UserCreate(
            username="testuser",
            email="test1@example.com",
            password="password123"
        )
        await auth_service.register_user(test_session, user_data1)
        
        # Try to create second user with same username
        user_data2 = UserCreate(
            username="testuser",
            email="test2@example.com",
            password="password456"
        )
        
        with pytest.raises(Exception) as exc_info:
            await auth_service.register_user(test_session, user_data2)
        
        assert "用户名已存在" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_user_registration_duplicate_email(self, test_session: AsyncSession):
        """Test registration with duplicate email"""
        # Create first user
        user_data1 = UserCreate(
            username="testuser1",
            email="test@example.com",
            password="password123"
        )
        await auth_service.register_user(test_session, user_data1)
        
        # Try to create second user with same email
        user_data2 = UserCreate(
            username="testuser2",
            email="test@example.com",
            password="password456"
        )
        
        with pytest.raises(Exception) as exc_info:
            await auth_service.register_user(test_session, user_data2)
        
        assert "邮箱已被注册" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_user_login_success(self, test_session: AsyncSession):
        """Test successful user login"""
        # Register user first
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        await auth_service.register_user(test_session, user_data)
        
        # Login with username
        login_data = UserLogin(
            username="testuser",
            password="password123"
        )
        
        result = await auth_service.login_user(test_session, login_data)
        
        assert result.access_token is not None
        assert result.token_type == "bearer"
        assert result.expires_in > 0
        assert result.user.username == "testuser"
        assert result.user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_user_login_with_email(self, test_session: AsyncSession):
        """Test login with email instead of username"""
        # Register user first
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        await auth_service.register_user(test_session, user_data)
        
        # Login with email
        login_data = UserLogin(
            username="test@example.com",  # Using email as username
            password="password123"
        )
        
        result = await auth_service.login_user(test_session, login_data)
        
        assert result.access_token is not None
        assert result.user.username == "testuser"
        assert result.user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_user_login_wrong_password(self, test_session: AsyncSession):
        """Test login with wrong password"""
        # Register user first
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        await auth_service.register_user(test_session, user_data)
        
        # Try to login with wrong password
        login_data = UserLogin(
            username="testuser",
            password="wrongpassword"
        )
        
        with pytest.raises(Exception) as exc_info:
            await auth_service.login_user(test_session, login_data)
        
        assert "用户名或密码错误" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_user_login_nonexistent_user(self, test_session: AsyncSession):
        """Test login with nonexistent user"""
        login_data = UserLogin(
            username="nonexistent",
            password="password123"
        )
        
        with pytest.raises(Exception) as exc_info:
            await auth_service.login_user(test_session, login_data)
        
        assert "用户名或密码错误" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_token_verification_valid(self, test_session: AsyncSession):
        """Test token verification with valid token"""
        # Register and login user
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        await auth_service.register_user(test_session, user_data)
        
        login_data = UserLogin(
            username="testuser",
            password="password123"
        )
        token_result = await auth_service.login_user(test_session, login_data)
        
        # Verify token
        user = await auth_service.get_current_user(test_session, token_result.access_token)
        
        assert user is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_token_verification_invalid(self, test_session: AsyncSession):
        """Test token verification with invalid token"""
        invalid_token = "invalid.token.here"
        
        user = await auth_service.get_current_user(test_session, invalid_token)
        
        assert user is None
    
    @pytest.mark.asyncio
    async def test_user_logout(self, test_session: AsyncSession):
        """Test user logout"""
        # Register and login user
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        registered_user = await auth_service.register_user(test_session, user_data)
        
        login_data = UserLogin(
            username="testuser",
            password="password123"
        )
        token_result = await auth_service.login_user(test_session, login_data)
        
        # Logout user
        success = await auth_service.logout_user(registered_user.id)
        
        assert success is True
        
        # Verify token is no longer valid (session should be cleared)
        user = await auth_service.get_current_user(test_session, token_result.access_token)
        assert user is None


class TestAuthenticationAPI:
    """Test authentication API endpoints"""
    
    @pytest.mark.asyncio
    async def test_register_endpoint(self, override_get_db):
        """Test registration API endpoint"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            })
            
            assert response.status_code == 201
            data = response.json()
            assert data["username"] == "testuser"
            assert data["email"] == "test@example.com"
            assert data["score"] == 0
            assert "id" in data
    
    @pytest.mark.asyncio
    async def test_register_endpoint_duplicate(self, override_get_db):
        """Test registration API endpoint with duplicate user"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register first user
            await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            })
            
            # Try to register duplicate
            response = await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test2@example.com",
                "password": "password456"
            })
            
            assert response.status_code == 400
            data = response.json()
            assert "用户名已存在" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_login_endpoint(self, override_get_db):
        """Test login API endpoint"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register user first
            await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            })
            
            # Login
            response = await client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "password123"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert "expires_in" in data
            assert data["user"]["username"] == "testuser"
    
    @pytest.mark.asyncio
    async def test_login_endpoint_wrong_credentials(self, override_get_db):
        """Test login API endpoint with wrong credentials"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register user first
            await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            })
            
            # Try to login with wrong password
            response = await client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "wrongpassword"
            })
            
            assert response.status_code == 401
            data = response.json()
            assert "用户名或密码错误" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_profile_endpoint(self, override_get_db):
        """Test profile API endpoint"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register and login user
            await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            })
            
            login_response = await client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "password123"
            })
            token = login_response.json()["access_token"]
            
            # Get profile
            response = await client.get("/api/v1/auth/profile", headers={
                "Authorization": f"Bearer {token}"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "testuser"
            assert data["email"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_profile_endpoint_unauthorized(self, override_get_db):
        """Test profile API endpoint without authorization"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/auth/profile")
            
            assert response.status_code == 403  # No authorization header
    
    @pytest.mark.asyncio
    async def test_verify_token_endpoint(self, override_get_db):
        """Test token verification endpoint"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register and login user
            await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            })
            
            login_response = await client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "password123"
            })
            token = login_response.json()["access_token"]
            
            # Verify token
            response = await client.get("/api/v1/auth/verify", headers={
                "Authorization": f"Bearer {token}"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["username"] == "testuser"
    
    @pytest.mark.asyncio
    async def test_logout_endpoint(self, override_get_db):
        """Test logout API endpoint"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register and login user
            await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            })
            
            login_response = await client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "password123"
            })
            token = login_response.json()["access_token"]
            
            # Logout
            response = await client.post("/api/v1/auth/logout", headers={
                "Authorization": f"Bearer {token}"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "登出成功" in data["message"]


class TestPasswordValidation:
    """Test password validation"""
    
    def test_password_hashing(self):
        """Test password hashing and verification"""
        password = "testpass123"
        hashed = auth_service.hash_password(password)
        
        assert hashed != password
        assert auth_service.verify_password(password, hashed) is True
        assert auth_service.verify_password("wrongpassword", hashed) is False
    
    def test_token_creation_and_verification(self):
        """Test JWT token creation and verification"""
        data = {"sub": "user123", "username": "testuser"}
        token = auth_service.create_access_token(data)
        
        assert token is not None
        
        payload = auth_service.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        
        # Test invalid token
        invalid_payload = auth_service.verify_token("invalid.token.here")
        assert invalid_payload is None


class TestInputValidation:
    """Test input validation for user data"""
    
    @pytest.mark.asyncio
    async def test_invalid_username_format(self, override_get_db):
        """Test registration with invalid username format"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/register", json={
                "username": "test@user",  # Invalid characters
                "email": "test@example.com",
                "password": "password123"
            })
            
            assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_invalid_email_format(self, override_get_db):
        """Test registration with invalid email format"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "invalid-email",  # Invalid email format
                "password": "password123"
            })
            
            assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_weak_password(self, override_get_db):
        """Test registration with weak password"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "weak"  # Too short and no numbers
            })
            
            assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_short_username(self, override_get_db):
        """Test registration with too short username"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/register", json={
                "username": "ab",  # Too short
                "email": "test@example.com",
                "password": "password123"
            })
            
            assert response.status_code == 422  # Validation error