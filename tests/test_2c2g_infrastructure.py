"""
2C2G infrastructure tests
2C2G基础设施测试
"""

import pytest
import asyncio
from app.utils.resource_monitor import resource_monitor
from app.utils.system_health import health_monitor, HealthStatus
from app.core.config import settings


class Test2C2GInfrastructure:
    """Test 2C2G specific infrastructure components"""
    
    def test_2c2g_settings(self):
        """Test that 2C2G specific settings are configured"""
        # Resource limits
        assert settings.MAX_MEMORY_MB <= 2048  # Should be reasonable for 2C2G
        assert settings.MAX_CPU_PERCENT <= 100
        assert settings.CLEANUP_INTERVAL > 0
        
        # Connection limits
        assert settings.DB_POOL_SIZE <= 10  # Limited for memory efficiency
        assert settings.REDIS_MAX_CONNECTIONS <= 10
        assert settings.MAX_WEBSOCKET_CONNECTIONS <= 100
        
        # Game limits
        assert settings.MAX_ROOMS <= 20  # Reasonable for 2C2G
        assert settings.MAX_PLAYERS_PER_ROOM <= 10
        
        # Worker configuration
        assert settings.WORKERS == 1  # Single worker for 2C2G
    
    @pytest.mark.asyncio
    async def test_resource_monitor_initialization(self):
        """Test resource monitor can be initialized"""
        monitor = resource_monitor
        assert monitor is not None
        assert monitor.max_memory_mb == settings.MAX_MEMORY_MB
        assert monitor.max_cpu_percent == settings.MAX_CPU_PERCENT
    
    @pytest.mark.asyncio
    async def test_resource_monitor_usage_check(self):
        """Test resource monitor can check current usage"""
        usage = resource_monitor.get_current_usage()
        
        assert "memory_mb" in usage
        assert "memory_percent" in usage
        assert "cpu_percent" in usage
        assert "memory_limit_mb" in usage
        assert "cpu_limit_percent" in usage
        
        assert usage["memory_mb"] >= 0
        assert usage["memory_percent"] >= 0
        assert usage["cpu_percent"] >= 0
        assert usage["memory_limit_mb"] == settings.MAX_MEMORY_MB
        assert usage["cpu_limit_percent"] == settings.MAX_CPU_PERCENT
    
    @pytest.mark.asyncio
    async def test_resource_availability_check(self):
        """Test resource availability checking"""
        # Should be available with reasonable memory request
        available = resource_monitor.is_resource_available(required_memory_mb=10)
        assert isinstance(available, bool)
        
        # Should not be available with excessive memory request
        excessive_memory = settings.MAX_MEMORY_MB * 2
        not_available = resource_monitor.is_resource_available(required_memory_mb=excessive_memory)
        assert not_available is False
    
    @pytest.mark.asyncio
    async def test_health_monitor_initialization(self):
        """Test health monitor can be initialized"""
        monitor = health_monitor
        assert monitor is not None
        assert monitor.check_interval > 0
    
    @pytest.mark.asyncio
    async def test_health_checks_execution(self):
        """Test health checks can be executed"""
        checks = await health_monitor.run_health_checks()
        
        assert isinstance(checks, list)
        assert len(checks) > 0
        
        # Check that all expected health checks are present
        check_names = [check.name for check in checks]
        expected_checks = ["resources", "database", "redis", "application"]
        
        for expected in expected_checks:
            assert expected in check_names
    
    @pytest.mark.asyncio
    async def test_health_report_generation(self):
        """Test health report generation"""
        await health_monitor.run_health_checks()
        report = health_monitor.get_health_report()
        
        assert "overall_status" in report
        assert "last_check" in report
        assert "checks" in report
        assert "environment" in report
        assert "resource_limits" in report
        
        assert report["overall_status"] in [
            HealthStatus.HEALTHY, 
            HealthStatus.WARNING, 
            HealthStatus.CRITICAL, 
            HealthStatus.UNKNOWN
        ]
        
        assert report["environment"] == settings.ENVIRONMENT
        
        # Check resource limits are included
        limits = report["resource_limits"]
        assert limits["max_memory_mb"] == settings.MAX_MEMORY_MB
        assert limits["max_cpu_percent"] == settings.MAX_CPU_PERCENT
        assert limits["max_rooms"] == settings.MAX_ROOMS
        assert limits["max_websocket_connections"] == settings.MAX_WEBSOCKET_CONNECTIONS
    
    @pytest.mark.asyncio
    async def test_enhanced_health_endpoint(self):
        """Test enhanced health endpoint with 2C2G monitoring"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            
            data = response.json()
            assert "status" in data
            assert "version" in data
            assert "environment" in data
            assert "health_checks" in data
            assert "resource_usage" in data
            assert "limits" in data
            
            # Check resource usage data
            resource_usage = data["resource_usage"]
            assert "memory_mb" in resource_usage
            assert "cpu_percent" in resource_usage
            
            # Check limits data
            limits = data["limits"]
            assert "max_memory_mb" in limits
            assert "max_cpu_percent" in limits
    
    @pytest.mark.asyncio
    async def test_resource_endpoint(self):
        """Test resource monitoring endpoint"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/resources")
            assert response.status_code == 200
            
            data = response.json()
            assert "usage" in data
            assert "available" in data
            assert "optimized_for" in data
            
            assert data["optimized_for"] == "2C2G server environment"
            assert isinstance(data["available"], bool)
            
            usage = data["usage"]
            assert "memory_mb" in usage
            assert "cpu_percent" in usage
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Test monitoring start/stop lifecycle"""
        # Test resource monitor lifecycle
        await resource_monitor.start_monitoring()
        assert resource_monitor._monitoring is True
        
        await resource_monitor.stop_monitoring()
        assert resource_monitor._monitoring is False
        
        # Test health monitor lifecycle
        await health_monitor.start_monitoring()
        assert health_monitor._monitoring is True
        
        await health_monitor.stop_monitoring()
        assert health_monitor._monitoring is False
    
    def test_2c2g_docker_configuration(self):
        """Test Docker configuration is optimized for 2C2G"""
        import os
        
        # Check if docker-compose.yml exists and has resource limits
        if os.path.exists("docker-compose.yml"):
            with open("docker-compose.yml", "r") as f:
                content = f.read()
                assert "memory:" in content  # Should have memory limits
                assert "cpus:" in content    # Should have CPU limits
    
    def test_mysql_configuration_2c2g(self):
        """Test MySQL configuration is optimized for 2C2G"""
        import os
        
        if os.path.exists("mysql.cnf"):
            with open("mysql.cnf", "r") as f:
                content = f.read()
                # Check for 2C2G optimizations
                assert "innodb_buffer_pool_size" in content
                assert "max_connections" in content
                assert "performance_schema = OFF" in content  # Disabled to save memory
    
    def test_redis_configuration_2c2g(self):
        """Test Redis configuration is optimized for 2C2G"""
        import os
        
        if os.path.exists("redis.conf"):
            with open("redis.conf", "r") as f:
                content = f.read()
                # Check for 2C2G optimizations
                assert "maxmemory" in content
                assert "maxmemory-policy" in content
                assert "maxclients" in content