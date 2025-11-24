import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from main import app
from database import Base, get_db

# Uso do SQLite para testes
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_user(client):
    """Test creating a new user"""
    response = client.post("/users", json={"name": "John Doe"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "John Doe"
    assert "id" in data
    assert "created_at" in data


def test_create_user_invalid_name(client):
    """Test creating user with invalid name"""
    response = client.post("/users", json={"name": ""})
    assert response.status_code == 422


def test_get_current_user_without_auth(client):
    """Test getting current user without authorization header"""
    response = client.get("/users/me")
    assert response.status_code == 422


def test_get_current_user_with_invalid_auth(client):
    """Test getting current user with invalid authorization"""
    response = client.get("/users/me", headers={"Authorization": "invalid"})
    assert response.status_code == 401


def test_get_current_user_not_found(client):
    """Test getting current user that doesn't exist"""
    response = client.get("/users/me", headers={"Authorization": "999"})
    assert response.status_code == 401
    assert response.json()["detail"] == "User not found"


def test_get_current_user(client):
    """Test getting current user with valid authorization"""

    create_response = client.post("/users", json={"name": "Jane Doe"})
    user_id = create_response.json()["id"]

    response = client.get("/users/me", headers={"Authorization": str(user_id)})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Jane Doe"
    assert data["id"] == user_id


def test_create_account(client):
    """Test creating an account"""

    user_response = client.post("/users", json={"name": "Alice"})
    user_id = user_response.json()["id"]


    response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000.00"},
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["account_type"] == "savings"
    assert data["currency"] == "USD"
    assert data["balance"] == "1000.00"
    assert data["user_id"] == user_id


def test_create_account_without_auth(client):
    """Test creating account without authentication"""
    response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD"}
    )
    assert response.status_code == 422


def test_create_account_default_balance(client):
    """Test creating account with default balance"""

    user_response = client.post("/users", json={"name": "Bob"})
    user_id = user_response.json()["id"]


    response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "EUR"},
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 201
    assert response.json()["balance"] == "0.00"


def test_list_accounts(client):
    """Test listing user accounts"""

    user_response = client.post("/users", json={"name": "Charlie"})
    user_id = user_response.json()["id"]


    client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "500"},
        headers={"Authorization": str(user_id)}
    )
    client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "EUR", "balance": "1000"},
        headers={"Authorization": str(user_id)}
    )


    response = client.get("/accounts", headers={"Authorization": str(user_id)})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_account(client):
    """Test getting a specific account"""

    user_response = client.post("/users", json={"name": "David"})
    user_id = user_response.json()["id"]

    account_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "GBP", "balance": "2000"},
        headers={"Authorization": str(user_id)}
    )
    account_id = account_response.json()["id"]


    response = client.get(
        f"/accounts/{account_id}",
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == account_id
    assert data["currency"] == "GBP"


def test_get_account_not_found(client):
    """Test getting non-existent account"""
    user_response = client.post("/users", json={"name": "Eve"})
    user_id = user_response.json()["id"]

    response = client.get(
        "/accounts/999",
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 404


def test_get_account_not_owned(client):
    """Test getting account not owned by user"""

    user1_response = client.post("/users", json={"name": "User1"})
    user1_id = user1_response.json()["id"]

    user2_response = client.post("/users", json={"name": "User2"})
    user2_id = user2_response.json()["id"]


    account_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000"},
        headers={"Authorization": str(user1_id)}
    )
    account_id = account_response.json()["id"]


    response = client.get(
        f"/accounts/{account_id}",
        headers={"Authorization": str(user2_id)}
    )
    assert response.status_code == 404


def test_transfer_same_user(client):
    """Test transfer between accounts of the same user"""

    user_response = client.post("/users", json={"name": "Frank"})
    user_id = user_response.json()["id"]


    account1_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000"},
        headers={"Authorization": str(user_id)}
    )
    account1_id = account1_response.json()["id"]

    account2_response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "USD", "balance": "500"},
        headers={"Authorization": str(user_id)}
    )
    account2_id = account2_response.json()["id"]

    response = client.post(
        "/transfers",
        json={
            "from_account_id": account1_id,
            "to_account_id": account2_id,
            "amount": "200.00"
        },
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == "200.00"
    assert data["from_account_id"] == account1_id
    assert data["to_account_id"] == account2_id


    acc1 = client.get(f"/accounts/{account1_id}", headers={"Authorization": str(user_id)})
    acc2 = client.get(f"/accounts/{account2_id}", headers={"Authorization": str(user_id)})

    assert acc1.json()["balance"] == "800.00"
    assert acc2.json()["balance"] == "700.00"


def test_transfer_different_users(client):
    """Test transfer between accounts of different users"""

    user1_response = client.post("/users", json={"name": "Grace"})
    user1_id = user1_response.json()["id"]

    user2_response = client.post("/users", json={"name": "Henry"})
    user2_id = user2_response.json()["id"]


    account1_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "EUR", "balance": "2000"},
        headers={"Authorization": str(user1_id)}
    )
    account1_id = account1_response.json()["id"]

    account2_response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "EUR", "balance": "1000"},
        headers={"Authorization": str(user2_id)}
    )
    account2_id = account2_response.json()["id"]

    response = client.post(
        "/transfers",
        json={
            "from_account_id": account1_id,
            "to_account_id": account2_id,
            "amount": "500"
        },
        headers={"Authorization": str(user1_id)}
    )
    assert response.status_code == 201

    acc1 = client.get(f"/accounts/{account1_id}", headers={"Authorization": str(user1_id)})
    acc2 = client.get(f"/accounts/{account2_id}", headers={"Authorization": str(user2_id)})

    assert acc1.json()["balance"] == "1500.00"
    assert acc2.json()["balance"] == "1500.00"


def test_transfer_insufficient_balance(client):
    """Test transfer with insufficient balance"""

    user_response = client.post("/users", json={"name": "Ivy"})
    user_id = user_response.json()["id"]

    account1_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "100"},
        headers={"Authorization": str(user_id)}
    )
    account1_id = account1_response.json()["id"]

    account2_response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "USD", "balance": "0"},
        headers={"Authorization": str(user_id)}
    )
    account2_id = account2_response.json()["id"]

    response = client.post(
        "/transfers",
        json={
            "from_account_id": account1_id,
            "to_account_id": account2_id,
            "amount": "200"
        },
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 400
    assert "Insufficient balance" in response.json()["detail"]


def test_transfer_currency_mismatch(client):
    """Test transfer with different currencies"""

    user_response = client.post("/users", json={"name": "Jack"})
    user_id = user_response.json()["id"]

    account1_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000"},
        headers={"Authorization": str(user_id)}
    )
    account1_id = account1_response.json()["id"]

    account2_response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "EUR", "balance": "500"},
        headers={"Authorization": str(user_id)}
    )
    account2_id = account2_response.json()["id"]


    response = client.post(
        "/transfers",
        json={
            "from_account_id": account1_id,
            "to_account_id": account2_id,
            "amount": "100"
        },
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 400
    assert "Currency mismatch" in response.json()["detail"]


def test_transfer_to_same_account(client):
    """Test transfer to the same account"""

    user_response = client.post("/users", json={"name": "Kate"})
    user_id = user_response.json()["id"]

    account_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000"},
        headers={"Authorization": str(user_id)}
    )
    account_id = account_response.json()["id"]

    response = client.post(
        "/transfers",
        json={
            "from_account_id": account_id,
            "to_account_id": account_id,
            "amount": "100"
        },
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 400
    assert "Cannot transfer to the same account" in response.json()["detail"]


def test_transfer_not_owner(client):
    """Test transfer from account not owned by user"""

    user1_response = client.post("/users", json={"name": "Leo"})
    user1_id = user1_response.json()["id"]

    user2_response = client.post("/users", json={"name": "Mia"})
    user2_id = user2_response.json()["id"]


    account1_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000"},
        headers={"Authorization": str(user1_id)}
    )
    account1_id = account1_response.json()["id"]

    account2_response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "USD", "balance": "500"},
        headers={"Authorization": str(user2_id)}
    )
    account2_id = account2_response.json()["id"]


    response = client.post(
        "/transfers",
        json={
            "from_account_id": account1_id,
            "to_account_id": account2_id,
            "amount": "100"
        },
        headers={"Authorization": str(user2_id)}
    )
    assert response.status_code == 403
    assert "don't own the source account" in response.json()["detail"]


def test_transfer_invalid_amount(client):
    """Test transfer with invalid amount"""
    user_response = client.post("/users", json={"name": "Nina"})
    user_id = user_response.json()["id"]

    account1_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000"},
        headers={"Authorization": str(user_id)}
    )
    account1_id = account1_response.json()["id"]

    account2_response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "USD", "balance": "500"},
        headers={"Authorization": str(user_id)}
    )
    account2_id = account2_response.json()["id"]

    response = client.post(
        "/transfers",
        json={
            "from_account_id": account1_id,
            "to_account_id": account2_id,
            "amount": "0"
        },
        headers={"Authorization": str(user_id)}
    )
    assert response.status_code == 422


def test_list_transfers(client):
    """Test listing transfers"""

    user_response = client.post("/users", json={"name": "Oscar"})
    user_id = user_response.json()["id"]

    account1_response = client.post(
        "/accounts",
        json={"account_type": "savings", "currency": "USD", "balance": "1000"},
        headers={"Authorization": str(user_id)}
    )
    account1_id = account1_response.json()["id"]

    account2_response = client.post(
        "/accounts",
        json={"account_type": "checking", "currency": "USD", "balance": "500"},
        headers={"Authorization": str(user_id)}
    )
    account2_id = account2_response.json()["id"]


    client.post(
        "/transfers",
        json={
            "from_account_id": account1_id,
            "to_account_id": account2_id,
            "amount": "100"
        },
        headers={"Authorization": str(user_id)}
    )

    client.post(
        "/transfers",
        json={
            "from_account_id": account2_id,
            "to_account_id": account1_id,
            "amount": "50"
        },
        headers={"Authorization": str(user_id)}
    )


    response = client.get("/transfers", headers={"Authorization": str(user_id)})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
