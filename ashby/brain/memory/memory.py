import json
import os

MEMORY_DIR = os.path.expanduser("memory/users")

def _path(user_id):
    return os.path.join(MEMORY_DIR, f"{user_id}.json")

def _ensure_dir():
    os.makedirs(MEMORY_DIR, exist_ok=True)

def load(user_id):
    _ensure_dir()
    path = _path(user_id)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save(user_id, data):
    _ensure_dir()
    path = _path(user_id)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get(user_id, key, default=None):
    data = load(user_id)
    return data.get(key, default)

def set(user_id, key, value):
    data = load(user_id)
    data[key] = value
    save(user_id, data)
