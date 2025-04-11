import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import json

from main import app
import crud
import models
import schemas
import logic

TEST_USER = {"email": "test@example.com"}
TEST_PROFILE = {
    "profile_data": {
        "contact": {
            "firstName": "Test",
            "lastName": "User",
            "email": "test@example.com",
            "phone": "555-1234"
        },
        "summary": "A testing profile.",
        "skills": ["pytest", "fastapi", "mocking"],
        "experience": [
            {"company": "TestCorp", "title": "Tester", "years": 1}
        ]
    }
}
TEST_JOB = {
    "title": "Test Engineer",
    "company": "TestCorp",
    "description_text": "Need someone to write tests. FastAPI knowledge a plus."
}

def setup_test_data(db_session: Session) -> int:
    user = crud.create_user(db_session, schemas.UserCreate(**TEST_USER))
    crud.create_or_update_user_profile(db_session, user.id, schemas.UserProfileCreate(**TEST_PROFILE))
    job = crud.create_job(db_session, schemas.JobCreate(**TEST_JOB), user.id)
    return job.id

@pytest.fixture(scope="function")
def setup_data_fixture(db_session: Session, request):
    test_name = request.function.__name__
    user_data = TEST_USER.copy()
    user_data["email"] = f"{test_name}@example.com"
    
    user = crud.create_user(db_session, schemas.UserCreate(**user_data))
    
    profile_data = TEST_PROFILE.copy()
    profile_data["profile_data"] = dict(TEST_PROFILE["profile_data"])
    profile_data["profile_data"]["contact"] = dict(TEST_PROFILE["profile_data"]["contact"])
    profile_data["profile_data"]["contact"]["email"] = user_data["email"]
    
    crud.create_or_update_user_profile(db_session, user.id, schemas.UserProfileCreate(**profile_data))
    job = crud.create_job(db_session, schemas.JobCreate(**TEST_JOB), user.id)
    db_session.commit()
    return {"user_id": user.id, "job_id": job.id, "email": user_data["email"]}

def test_create_user(test_client: TestClient):
    response = test_client.post("/users/", json=TEST_USER)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == TEST_USER["email"]
    assert "id" in data

def test_create_profile(test_client: TestClient): 
    user_id = 1
    response = test_client.post(f"/users/{user_id}/profile/", json=TEST_PROFILE)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["profile_data"] == TEST_PROFILE["profile_data"]

def test_create_job(test_client: TestClient): 
    user_id = 1
    response = test_client.post(f"/users/{user_id}/jobs/", json=TEST_JOB)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == TEST_JOB["title"]
    assert data["company"] == TEST_JOB["company"]
    assert data["description_text"] == TEST_JOB["description_text"]
    assert data["user_id"] == user_id
    assert "id" in data

def test_rank_job_success(test_client: TestClient, setup_data_fixture, db_session, monkeypatch):
    job_id = setup_data_fixture["job_id"]
    user_id = setup_data_fixture["user_id"]
    mock_response = "Score: 7.5\nExplanation: Decent match based on skills."
    async def mock_call_gemini(*args, **kwargs):
        return mock_response
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    response = test_client.post(f"/jobs/{job_id}/rank")
    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 7.5
    assert data["explanation"] == "Decent match based on skills."
    db_session.expire_all()
    db_job = crud.get_job(db_session, job_id=job_id, user_id=user_id)
    assert db_job.ranking_score == 7.5
    assert db_job.ranking_explanation == "Decent match based on skills."

def test_rank_job_llm_failure(test_client: TestClient, setup_data_fixture, db_session, monkeypatch):
    job_id = setup_data_fixture["job_id"]
    user_id = setup_data_fixture["user_id"]
    async def mock_call_gemini(*args, **kwargs):
        return None
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    response = test_client.post(f"/jobs/{job_id}/rank")
    assert response.status_code == 500
    db_job = crud.get_job(db_session, job_id=job_id, user_id=user_id)
    db_session.refresh(db_job)
    assert db_job.ranking_score is None
    assert db_job.ranking_explanation is None

def test_rank_job_parse_failure(test_client: TestClient, setup_data_fixture, db_session, monkeypatch):
    job_id = setup_data_fixture["job_id"]
    user_id = setup_data_fixture["user_id"]
    async def mock_call_gemini(*args, **kwargs):
        return "Score: ?? Explanation: ??"
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    response = test_client.post(f"/jobs/{job_id}/rank")
    assert response.status_code == 500
    db_job = crud.get_job(db_session, job_id=job_id, user_id=user_id)
    db_session.refresh(db_job)
    assert db_job.ranking_score is None
    assert db_job.ranking_explanation is None

def test_suggest_tailoring_success(test_client: TestClient, monkeypatch):
    mock_suggestions = "- Suggestion 1\n- Suggestion 2"
    async def mock_call_gemini(*args, **kwargs):
        return mock_suggestions
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    request_data = {
        "job_description": "Job desc...",
        "profile_snippet": "Profile snippet..."
    }
    response = test_client.post("/resume/suggest_tailoring", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["suggestions"] == mock_suggestions

def test_suggest_tailoring_llm_failure(test_client: TestClient, monkeypatch):
    async def mock_call_gemini(*args, **kwargs):
        return None
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    request_data = {
        "job_description": "Job desc...",
        "profile_snippet": "Profile snippet..."
    }
    response = test_client.post("/resume/suggest_tailoring", json=request_data)
    assert response.status_code == 500
    assert "Failed to generate resume tailoring suggestions" in response.text

def test_autofill_map_success(test_client: TestClient, setup_data_fixture, db_session, monkeypatch):
    user_id = setup_data_fixture["user_id"]
    form_fields_request = [
        {"field_id": "field_fname", "label": "First Name"},
        {"field_id": "field_email", "label": "Email"},
        {"field_id": "field_company", "label": "Company"},
        {"field_id": "field_skill_1", "label": "Skill 1"},
        {"field_id": "field_nonexistent", "label": "Something Else"},
        {"field_id": "field_badkey", "label": "Bad Key Test"}
    ]
    mock_key_mapping = {
        "field_fname": "contact.firstName",
        "field_email": "contact.email",
        "field_company": "experience.0.company",
        "field_skill_1": "skills.0",
        "field_nonexistent": "does.not.exist",
        "field_badkey": 123
    }
    async def mock_call_gemini(*args, **kwargs):
        assert kwargs.get('expect_json') is True
        return mock_key_mapping
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    response = test_client.post(f"/autofill/map_poc?user_id={user_id}", json=form_fields_request)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["field_fname"] == "Test"
    assert data["field_email"] == setup_data_fixture["email"]
    assert data["field_company"] == "TestCorp"
    assert data["field_skill_1"] == "pytest"
    assert "field_nonexistent" not in data
    assert "field_badkey" not in data

def test_autofill_map_llm_failure_json(test_client: TestClient, setup_data_fixture, db_session, monkeypatch):
    user_id = setup_data_fixture["user_id"]
    async def mock_call_gemini(*args, **kwargs):
        assert kwargs.get('expect_json') is True
        return None
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    form_fields_request = [{"field_id": "f1", "label": "L1"}]
    response = test_client.post(f"/autofill/map_poc?user_id={user_id}", json=form_fields_request)
    assert response.status_code == 200
    assert response.json() == {}

def test_autofill_map_llm_invalid_json(test_client: TestClient, setup_data_fixture, db_session, monkeypatch):
    user_id = setup_data_fixture["user_id"]
    async def mock_call_gemini(*args, **kwargs):
        assert kwargs.get('expect_json') is True
        return "this is not json"
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    form_fields_request = [{"field_id": "f1", "label": "L1"}]
    response = test_client.post(f"/autofill/map_poc?user_id={user_id}", json=form_fields_request)
    assert response.status_code == 200
    assert response.json() == {}

def test_autofill_map_no_profile(test_client: TestClient, db_session: Session, monkeypatch):
    user = crud.create_user(db_session, schemas.UserCreate(email="no_profile@example.com"))
    db_session.commit()
    user_id = user.id
    async def mock_call_gemini(*args, **kwargs):
        pytest.fail("LLM should not be called if profile is missing")
    monkeypatch.setattr(logic, "call_gemini", mock_call_gemini)
    form_fields_request = [{"field_id": "f1", "label": "L1"}]
    response = test_client.post(f"/autofill/map_poc?user_id={user_id}", json=form_fields_request)
    assert response.status_code == 404
    assert "Profile not found for user" in response.json()["detail"]
