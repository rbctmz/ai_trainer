from data.garmin_client import GarminClient


class DummyGarminSettingsClient:
    display_name = "Greg"
    full_name = "Greg Kisel"

    def __init__(self, payload):
        self.payload = payload

    def get_user_profile(self):
        return self.payload


def test_get_user_profile_enriches_garminconnect_settings_payload():
    client = GarminClient()
    client.is_authenticated = True
    client.client = DummyGarminSettingsClient(
        {"userData": {"measurementSystem": "metric"}}
    )

    profile = client.get_user_profile()

    assert profile["displayName"] == "Greg"
    assert profile["display_name"] == "Greg"
    assert profile["fullName"] == "Greg Kisel"
    assert profile["full_name"] == "Greg Kisel"
    assert profile["userData"]["measurementSystem"] == "metric"


def test_get_user_profile_preserves_existing_profile_names():
    client = GarminClient()
    client.is_authenticated = True
    client.client = DummyGarminSettingsClient(
        {"displayName": "Actual", "fullName": "Actual Name"}
    )

    profile = client.get_user_profile()

    assert profile["displayName"] == "Actual"
    assert profile["fullName"] == "Actual Name"
