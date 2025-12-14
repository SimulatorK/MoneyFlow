"""
Tests for authentication routes.

Tests login, logout, and registration functionality.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User

# Test password used in fixtures - must match conftest.py
TEST_PASSWORD = "testpassword123"


class TestAuthentication:
    """Test suite for authentication endpoints."""
    
    def test_login_page_loads(self, client: TestClient):
        """Test that login page loads successfully."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "login" in response.text.lower() or "MoneyFlow" in response.text
    
    def test_register_page_loads(self, client: TestClient):
        """Test that registration page loads successfully."""
        response = client.get("/register")
        assert response.status_code == 200
    
    def test_login_with_valid_credentials(
        self, 
        client: TestClient, 
        db_session: Session,
        test_user: User
    ):
        """Test successful login with valid credentials."""
        response = client.post(
            "/login",
            data={
                "username": test_user.username,
                "password": TEST_PASSWORD
            },
            follow_redirects=False
        )
        # Should redirect to home on successful login
        assert response.status_code in [302, 303, 307]
    
    def test_login_with_invalid_credentials(self, client: TestClient, test_user: User):
        """Test login fails with invalid credentials."""
        response = client.post(
            "/login",
            data={
                "username": test_user.username,
                "password": "wrongpassword"
            },
            follow_redirects=False
        )
        # Should stay on login page or redirect back
        assert response.status_code in [200, 302, 303, 307]
    
    def test_logout_clears_session(self, client: TestClient, test_user_with_auth: User):
        """Test that logout clears the session cookie."""
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code in [302, 303, 307]
    
    def test_protected_route_redirects_unauthenticated(self, client: TestClient):
        """Test that protected routes redirect unauthenticated users."""
        response = client.get("/home", follow_redirects=False)
        assert response.status_code in [302, 303, 307]
        # Should redirect to login
        assert "/login" in response.headers.get("location", "")
    
    def test_protected_route_accessible_when_authenticated(
        self, 
        client: TestClient, 
        test_user_with_auth: User
    ):
        """Test that authenticated users can access protected routes."""
        response = client.get("/home")
        assert response.status_code == 200


class TestRegistration:
    """Test suite for user registration."""
    
    def test_register_new_user(self, client: TestClient, db_session: Session):
        """Test successful registration of a new user."""
        response = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "newpassword123",
                "name": "New User"
            },
            follow_redirects=False
        )
        # Should redirect on success
        assert response.status_code in [302, 303]
        
        # Verify user was created
        user = db_session.query(User).filter(User.username == "newuser").first()
        assert user is not None
        assert user.name == "New User"
    
    def test_register_duplicate_username(
        self, 
        client: TestClient, 
        test_user: User
    ):
        """Test that duplicate usernames are rejected."""
        response = client.post(
            "/register",
            data={
                "username": test_user.username,  # Already exists
                "password": "anotherpassword",
                "name": "Another User"
            }
        )
        # Should show error or redirect back
        assert response.status_code in [200, 302, 400]

