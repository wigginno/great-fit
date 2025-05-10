import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import AsyncMock, patch, MagicMock
import stripe
import json
from typing import Optional

import models
import crud
import schemas
from main import process_job_in_background, app, get_current_user, get_settings
from settings import Settings

# --- Test User Creation Helper ---
def create_test_user(db: Session, email: str = "test@example.com", credits: int = 10) -> models.User:
    """Helper to create a user directly in the test database."""
    cognito_sub = f"sub-for-{email.replace('@', '-')}"
    user = models.User(email=email, cognito_sub=cognito_sub, credits=credits)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

# --- Tests ---

@pytest.mark.asyncio
async def test_process_job_insufficient_credits(db_session: Session):
    """
    Test processing a job when the user has 0 credits.
    Should not create job and not deduct credits.
    """
    # 1. Arrange: Create user with 0 credits
    user = create_test_user(db_session, email="lowcredit@example.com", credits=0)
    markdown_content = "# Job That Fails\nInsufficient credits."

    # Mock the connection manager's send method (used for error reporting)
    mock_manager = AsyncMock()
    mock_manager.send_personal_message = AsyncMock()

    # 2. Act: Call the background task directly with async mocks for logic functions to avoid await issues
    with patch("main.logic.clean_job_description", new_callable=AsyncMock, return_value=schemas.CleanedJobDescription(company="Test Co", title="Tester", location="Remote", cleaned_markdown="# Cleaned MD")) as mock_clean, \
         patch("main.logic.rank_job_with_llm", new_callable=AsyncMock, return_value=(85, "Good fit")) as mock_rank, \
         patch("main.logic.generate_tailoring_suggestions", new_callable=AsyncMock, return_value=["Suggestion 1"]) as mock_tailor:
        await process_job_in_background(user.id, markdown_content, mock_manager)

    # 3. Assert
    # Check credits didn't change
    db_session.refresh(user)
    assert user.credits == 0

    # Check no job was created
    jobs = crud.get_jobs_for_user(db=db_session, user_id=user.id)
    assert len(jobs) == 0

    # Check that an error message was sent via the manager
    mock_manager.send_personal_message.assert_awaited_once()

@pytest.mark.asyncio
async def test_process_job_sufficient_credits(db_session: Session):
    """
    Test processing a job when the user has sufficient credits.
    Should create the job and deduct 1 credit.
    """
    # 1. Arrange
    user = create_test_user(db_session, email="goodcredit2@example.com", credits=5)
    initial_credits = user.credits
    markdown_content = "# Real Job\nTesting credit deduction."

    # Mock the connection manager
    mock_manager = AsyncMock()
    mock_manager.send_personal_message = AsyncMock()

    # Mock external calls *within* process_job_in_background with AsyncMock to allow awaiting
    with patch("main.logic.clean_job_description", new_callable=AsyncMock, return_value=schemas.CleanedJobDescription(company="Test Co", title="Tester", location="Remote", cleaned_markdown="# Cleaned MD")) as mock_clean, \
         patch("main.logic.rank_job_with_llm", new_callable=AsyncMock, return_value=(85, "Good fit")) as mock_rank, \
         patch("main.logic.generate_tailoring_suggestions", new_callable=AsyncMock, return_value=["Suggestion 1"]) as mock_tailor:

        # 2. Act: Call the actual background task function
        # Pass the test session to the background task
        await process_job_in_background(user.id, markdown_content, mock_manager, db_session)

        # 3. Assert
        # Assert credits were deducted
        updated_user = crud.get_user_by_id(db=db_session, user_id=user.id)
        assert updated_user is not None, "User not found after background task."
        assert updated_user.credits == initial_credits - 1

        # Assert job was created
        jobs = crud.get_jobs_for_user(db=db_session, user_id=user.id)
        assert len(jobs) == 1
        assert jobs[0].company == "Test Co"
        assert jobs[0].score == 85
        assert jobs[0].tailoring_suggestions == ["Suggestion 1"]

        # Assert mocks for logic were called
        mock_clean.assert_awaited_once()
        mock_rank.assert_awaited_once()
        mock_tailor.assert_awaited_once()

# --- Billing Endpoint Tests --- #

# Mock settings for Stripe configuration
MOCK_SETTINGS = Settings(
    stripe_secret_key="sk_test_123",
    stripe_price_id_50_credits="price_123",
    stripe_webhook_secret="whsec_test_123",
    app_base_url="http://testserver",
    cognito_user_pool_id=None, 
    cognito_app_client_id=None,
    cognito_domain=None,
    openrouter_api_key=None,
)

@pytest.mark.asyncio
async def test_create_checkout_session(test_client: TestClient, db_session: Session):
    """Test creating a Stripe checkout session."""
    # 1. Arrange
    user = create_test_user(db_session, email="checkout@example.com", credits=5)
    expected_checkout_url = "https://checkout.stripe.com/pay/cs_test_123"

    # Mock get_current_user dependency to return our test user
    def override_get_current_user():
        return user
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Mock get_settings dependency
    def override_get_settings():
        return MOCK_SETTINGS
    app.dependency_overrides[get_settings] = override_get_settings

    # Mock Stripe API call
    with patch("main.stripe.checkout.Session.create", new_callable=AsyncMock) as mock_stripe_create:
        # Use MagicMock for the return value to easily set attributes
        mock_session = MagicMock()
        mock_session.url = expected_checkout_url
        mock_stripe_create.return_value = mock_session

        # 2. Act
        # Use test_client which handles async calls correctly
        response = test_client.post("/billing/checkout-session")

        # 3. Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"url": expected_checkout_url}

        # Assert Stripe's create was called correctly
        mock_stripe_create.assert_called_once() 
        call_args, call_kwargs = mock_stripe_create.call_args
        assert call_kwargs["line_items"][0]["price"] == MOCK_SETTINGS.stripe_price_id_50_credits
        assert call_kwargs["mode"] == "payment"
        assert call_kwargs["metadata"]["user_id"] == str(user.id)
        assert "success_url" in call_kwargs
        assert "cancel_url" in call_kwargs
        assert call_kwargs["success_url"].startswith(MOCK_SETTINGS.app_base_url)
        assert call_kwargs["cancel_url"].startswith(MOCK_SETTINGS.app_base_url)

    # Cleanup dependency overrides
    del app.dependency_overrides[get_current_user]
    del app.dependency_overrides[get_settings]

# --- Webhook Tests --- #

# Helper to create a mock Stripe event
def create_mock_stripe_event(event_type: str, user_id: Optional[int] = None) -> dict:
    event_data = {
        "id": "evt_test_webhook",
        "object": "event",
        "type": event_type,
        "data": {
            "object": {
                "id": "cs_test_123",
                "object": "checkout.session",
                "payment_status": "paid",
                "metadata": {"user_id": str(user_id)} if user_id else {},
            }
        },
    }
    return event_data

@pytest.mark.asyncio
async def test_stripe_webhook_success(test_client: TestClient, db_session: Session):
    """Test successful processing of checkout.session.completed webhook."""
    # 1. Arrange
    user = create_test_user(db_session, email="webhook@example.com", credits=10)
    initial_credits = user.credits
    mock_event = create_mock_stripe_event("checkout.session.completed", user.id)
    payload = json.dumps(mock_event).encode('utf-8')
    headers = {"Stripe-Signature": "t=123,v1=dummy_signature"} 

    # Mock get_settings
    def override_get_settings():
        return MOCK_SETTINGS
    app.dependency_overrides[get_settings] = override_get_settings

    # Mock Stripe webhook construction
    with patch("main.stripe.Webhook.construct_event") as mock_construct_event:
        mock_construct_event.return_value = mock_event

        # 2. Act
        response = test_client.post("/billing/webhook", content=payload, headers=headers)

        # 3. Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "success"}

        # Verify credits were added
        db_session.refresh(user) 
        assert user.credits == initial_credits + 50

    # Cleanup
    del app.dependency_overrides[get_settings]

@pytest.mark.asyncio
async def test_stripe_webhook_invalid_signature(test_client: TestClient, db_session: Session):
    """Test webhook processing with an invalid signature."""
    mock_event = create_mock_stripe_event("checkout.session.completed", 999) 
    payload = json.dumps(mock_event).encode('utf-8')
    headers = {"Stripe-Signature": "t=123,v1=invalid_signature"}

    # Mock get_settings
    def override_get_settings():
        return MOCK_SETTINGS
    app.dependency_overrides[get_settings] = override_get_settings

    # Mock Stripe webhook construction to raise SignatureVerificationError
    with patch("main.stripe.Webhook.construct_event") as mock_construct_event:
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError("Invalid signature", "sig_header")

        # 2. Act
        response = test_client.post("/billing/webhook", content=payload, headers=headers)

        # 3. Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid signature" in response.json()["detail"]

    # Cleanup
    del app.dependency_overrides[get_settings]

@pytest.mark.asyncio
async def test_stripe_webhook_missing_user_id(test_client: TestClient, db_session: Session):
    """Test webhook processing when user_id is missing from metadata."""
    mock_event = create_mock_stripe_event("checkout.session.completed", user_id=None) 
    payload = json.dumps(mock_event).encode('utf-8')
    headers = {"Stripe-Signature": "t=123,v1=dummy_signature"}

    # Mock get_settings
    def override_get_settings():
        return MOCK_SETTINGS
    app.dependency_overrides[get_settings] = override_get_settings

    # Mock Stripe webhook construction
    with patch("main.stripe.Webhook.construct_event") as mock_construct_event:
        mock_construct_event.return_value = mock_event

        # 2. Act
        response = test_client.post("/billing/webhook", content=payload, headers=headers)

        # 3. Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "error"
        assert "Missing user_id" in response.json()["detail"]
        # Importantly, no user credits should have changed (though we can't easily check ALL users)

    # Cleanup
    del app.dependency_overrides[get_settings]

@pytest.mark.asyncio
async def test_stripe_webhook_user_not_found(test_client: TestClient, db_session: Session):
    """Test webhook processing when user_id in metadata doesn't exist."""
    non_existent_user_id = 99999
    mock_event = create_mock_stripe_event("checkout.session.completed", user_id=non_existent_user_id)
    payload = json.dumps(mock_event).encode('utf-8')
    headers = {"Stripe-Signature": "t=123,v1=dummy_signature"}

    # Mock get_settings
    def override_get_settings():
        return MOCK_SETTINGS
    app.dependency_overrides[get_settings] = override_get_settings

    # Mock Stripe webhook construction
    with patch("main.stripe.Webhook.construct_event") as mock_construct_event:
        mock_construct_event.return_value = mock_event

        # 2. Act
        response = test_client.post("/billing/webhook", content=payload, headers=headers)

        # 3. Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "success"} 

        # Verify no user was created or modified (check count or specific non-existent ID)
        user_check = crud.get_user_by_id(db_session, non_existent_user_id)
        assert user_check is None

    # Cleanup
    del app.dependency_overrides[get_settings]

@pytest.mark.asyncio
async def test_stripe_webhook_unhandled_event(test_client: TestClient, db_session: Session):
    """Test webhook processing for an unhandled event type."""
    mock_event = create_mock_stripe_event("payment_intent.succeeded") 
    payload = json.dumps(mock_event).encode('utf-8')
    headers = {"Stripe-Signature": "t=123,v1=dummy_signature"}

    # Mock get_settings
    def override_get_settings():
        return MOCK_SETTINGS
    app.dependency_overrides[get_settings] = override_get_settings

    # Mock Stripe webhook construction
    with patch("main.stripe.Webhook.construct_event") as mock_construct_event:
        mock_construct_event.return_value = mock_event

        # 2. Act
        response = test_client.post("/billing/webhook", content=payload, headers=headers)

        # 3. Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "success"} 
        # No credits should have changed.

    # Cleanup
    del app.dependency_overrides[get_settings]
