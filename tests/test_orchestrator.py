from src.core.orchestrator import process_email_thread


def test_process_email_thread():
    # Sample email thread for testing
    email_thread = [
        {
            "from": "sales@sunrisehotel.com",
            "to": "your_email_reply_team@example.com",
            "subject": "Corporate stay plan (Oct–Dec) — quick check",
            "body": "We’re sharing a corporate stay plan for Oct–Dec. Are you interested?",
        },
        {
            "from": "your_email_reply_team@example.com",
            "to": "sales@sunrisehotel.com",
            "subject": "Re: Corporate stay plan (Oct–Dec) — quick check",
            "body": "Need details.",
        },
        {
            "from": "sales@sunrisehotel.com",
            "to": "your_email_reply_team@example.com",
            "subject": "Re: Corporate stay plan (Oct–Dec) — quick check",
            "body": "Interested. Can you share an updated price list?",
        },
    ]

    # Expected output after processing the email thread
    expected_output = {
        "recognized_intents": ["request_details", "show_interest"],
        "proposed_actions": ["send_price_list", "ask_for_dates"],
    }

    # Call the function to test
    output = process_email_thread(email_thread)

    # Assert that the output matches the expected output
    assert output == expected_output


def test_empty_email_thread():
    # Test with an empty email thread
    email_thread = []

    # Expected output for an empty thread
    expected_output = {"recognized_intents": [], "proposed_actions": []}

    # Call the function to test
    output = process_email_thread(email_thread)

    # Assert that the output matches the expected output
    assert output == expected_output


# Additional tests can be added here for more scenarios
