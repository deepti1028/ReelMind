from api.deps import CurrentUser


def test_current_user_is_dataclass():
    user = CurrentUser(id="abc", email="a@b.com")
    assert user.id == "abc"
    assert user.email == "a@b.com"
