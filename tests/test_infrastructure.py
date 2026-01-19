"""
Infrastructure tests
基础设施测试
"""

import pytest
from app.core.config import settings


class TestInfrastructure:
    """Test basic infrastructure setup"""
    
    def test_app_creation(self):
        """Test that FastAPI app is created successfully"""
        from app.main import app
        assert app is not None
        assert "谁是卧底" in app.title
        assert app.version == "1.0.0"
    
    def test_settings_loaded(self):
        """Test that settings are loaded correctly"""
        assert settings is not None
        assert settings.ENVIRONMENT is not None
        assert settings.DATABASE_URL is not None
        assert settings.REDIS_URL is not None
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            # Status can be healthy, warning, or critical depending on services availability
            assert data["status"] in ["healthy", "warning", "critical"]
            assert data["version"] == "1.0.0"
            assert "health_checks" in data
            assert "resource_usage" in data
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Test root endpoint"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert "谁是卧底" in data["message"]
            assert data["status"] == "running"
    
    @pytest.mark.asyncio
    async def test_api_health_endpoint(self):
        """Test API v1 health endpoint"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["version"] == "1.0.0"