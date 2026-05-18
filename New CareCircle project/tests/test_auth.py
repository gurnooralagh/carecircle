import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_set_role_creates_user_profile(db, test_user_token, test_user_id):
    response = client.post(
        "/api/auth/set-role",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={
            "role": "guardian",
            "full_name": "Meera Sharma",
            "phone": "9876543210",
            "email": "meera@test.com",
            "relationship": "daughter",
        },
    )
    print(f"\nSet-role response: {response.json()}")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "guardian"
    assert data["next_step"] == "onboarding"
    assert "user_profile_id" in data

    # Cleanup
    db.table("user_profiles").delete().eq("id", data["user_profile_id"]).execute()


def test_set_role_requires_auth():
    response = client.post(
        "/api/auth/set-role",
        json={"role": "guardian", "full_name": "Test"},
    )
    assert response.status_code == 403
