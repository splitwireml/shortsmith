import pytest

from app.storage import Storage


def test_put_read_list_size_delete(tmp_path):
    store = Storage(tmp_path / "media")
    store.put("videos/1/clip_0.mp4", b"aaa")
    store.put("videos/1/final.mp4", b"bbbbb")
    store.put("videos/2/thumb.png", b"cc")

    # No get(): the doc's interface reads through path(key).
    assert store.path("videos/1/final.mp4").read_bytes() == b"bbbbb"
    assert store.exists("videos/1/clip_0.mp4")
    assert sorted(store.list("videos/1/")) == ["videos/1/clip_0.mp4", "videos/1/final.mp4"]
    assert store.size("videos/1/") == 8
    assert store.size("videos/") == 10

    store.delete("videos/1/clip_0.mp4")
    assert not store.exists("videos/1/clip_0.mp4")
    assert store.list("videos/1/") == ["videos/1/final.mp4"]
    store.delete("videos/1/clip_0.mp4")  # S3-style: deleting a missing key is not an error


@pytest.mark.parametrize("key", ["../escape.mp4", "videos/../../escape.mp4", "/etc/passwd"])
def test_rejects_keys_outside_the_media_folder(tmp_path, key):
    store = Storage(tmp_path / "media")
    with pytest.raises(ValueError):
        store.put(key, b"x")
    with pytest.raises(ValueError):
        store.path(key)
    with pytest.raises(ValueError):
        store.delete(key)
    assert not (tmp_path / "escape.mp4").exists()
