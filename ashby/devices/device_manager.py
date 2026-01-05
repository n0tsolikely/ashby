# device_manager.py
# Centralized device lookup + filtering logic for Ashby.
# All other modules (router, intents, scenes, automations) should use THIS,
# instead of reading ashby_devices.DEVICES directly.

from . import ashby_devices


def get_device(name: str) -> dict | None:
    """Return a device by its key: 'bed_lamp', 'thor_bulb', etc."""
    return ashby_devices.DEVICES.get(name)


def find_devices(
    backend: str | None = None,
    category: str | None = None,
    room: str | None = None,
    role: str | None = None,
):
    """
    Flexible search over the device registry.
    Filter by any combination of:
        backend, category, room, role.
    Returns a dict of matching devices.
    """
    result = {}
    for dev_name, dev_info in ashby_devices.DEVICES.items():
        if backend is not None and dev_info.get("backend") != backend:
            continue
        if category is not None and dev_info.get("category") != category:
            continue
        if room is not None and dev_info.get("room") != room:
            continue
        if role is not None and dev_info.get("role") != role:
            continue
        result[dev_name] = dev_info
    return result


def devices_in_room(room: str):
    """Return all devices located in a given room."""
    return find_devices(room=room)


def devices_with_role(role: str, room: str | None = None):
    """
    Return all devices that have a specific role.
    If room is provided, restrict results to that room.
    """
    return find_devices(role=role, room=room)
