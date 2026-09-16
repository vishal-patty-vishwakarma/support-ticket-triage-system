import os
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint3"
os.environ["DATABASE_URL"] = "sqlite:///./test_auth_temp.db"

from app.core.security import create_access_token, decode_access_token
from app.database import Base, get_db
from app.main import app
from app.seed import seed_database

TEST_DB_PATH = "test_auth_temp.db"
test_engine = create_engine(
    f"sqlite:///./{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Create fresh schema and seed test data before running tests."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    seed_database(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
def client():
    """FastAPI TestClient with overridden get_db dependency."""
    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# 1. Valid demo-user login returns 200
def test_valid_login_returns_200(client):
    response = client.post(
        "/auth/login",
        json={"email": "demo@support.local", "password": "DemoPass123!"},
    )
    assert response.status_code == 200


# 2. Returned token_type is "bearer"
def test_login_returns_bearer_token_type(client):
    response = client.post(
        "/auth/login",
        json={"email": "demo@support.local", "password": "DemoPass123!"},
    )
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


# 3. JWT contains a valid subject (user ID as string)
def test_jwt_contains_valid_subject(client):
    response = client.post(
        "/auth/login",
        json={"email": "demo@support.local", "password": "DemoPass123!"},
    )
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert "sub" in payload
    assert payload["sub"] == "1"


# 4. Wrong password returns 401
def test_wrong_password_returns_401(client):
    response = client.post(
        "/auth/login",
        json={"email": "demo@support.local", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


# 5. Nonexistent email returns 401
def test_nonexistent_email_returns_401(client):
    response = client.post(
        "/auth/login",
        json={"email": "nonexistent@support.local", "password": "DemoPass123!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


# 6. Inactive user cannot log in
def test_inactive_user_cannot_login(client):
    response = client.post(
        "/auth/login",
        json={"email": "dave.inactive@support.local", "password": "DemoPass123!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


# 7. GET /auth/me with valid JWT returns the correct user
def test_get_me_with_valid_jwt(client):
    login_res = client.post(
        "/auth/login",
        json={"email": "demo@support.local", "password": "DemoPass123!"},
    )
    token = login_res.json()["access_token"]
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == "demo@support.local"
    assert user_data["name"] == "Demo Support Agent"
    assert user_data["role"] == "agent"
    assert user_data["is_active"] is True


# 8. GET /auth/me does not expose password_hash
def test_get_me_does_not_expose_password_hash(client):
    login_res = client.post(
        "/auth/login",
        json={"email": "demo@support.local", "password": "DemoPass123!"},
    )
    token = login_res.json()["access_token"]
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    user_data = response.json()
    assert "password_hash" not in user_data
    assert "password" not in user_data


# 9. GET /auth/me without token returns 401 or 403
def test_get_me_without_token_returns_401(client):
    response = client.get("/auth/me")
    assert response.status_code in (401, 403)


# 10. Malformed token returns 401
def test_get_me_with_malformed_token_returns_401(client):
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer malformed.invalid.token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


# 11. Expired token returns 401
def test_get_me_with_expired_token_returns_401(client):
    expired_token = create_access_token(
        subject="1", expires_delta=timedelta(seconds=-10)
    )
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


# 12. Token referencing nonexistent user returns 401
def test_token_with_nonexistent_user_returns_401(client):
    nonexistent_user_token = create_access_token(subject="999999")
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {nonexistent_user_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
