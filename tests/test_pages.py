import pytest

@pytest.mark.parametrize("path", ["/", "/students", "/face-registration", "/face-attendance", "/schedules",
                                  "/attendance", "/logs", "/api/dashboard/stats"])
def test_pages_render(admin_client, path):
    assert admin_client.get(path).status_code == 200
