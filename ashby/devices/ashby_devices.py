# ashby_devices.py
# Pure device registry for THIS house.
# No helper functions, no logic — just structured device data.

DEVICES = {
    # ------------------------
    # PLUGS
    # ------------------------
    "bed_lamp": {
        "backend": "tuya",
        "category": "plug",
        "type": "generic_smart_plug",
        "id": "ebf157ec2f48cf767auaif",
        "room": "bedroom",
        "role": "bed_lamp",
        "description": "Bedside lamp outlet",
    },

    "birdcage_light": {
        "backend": "tuya",
        "category": "plug",
        "type": "generic_smart_plug",
        "id": "ebca18fe0ff83bec80tjtl",
        "room": "bedroom",
        "role": "pet_light",
        "description": "Birdcage light outlet",
    },

    # ------------------------
    # SMART BULBS (MARVEL SET)
    # ------------------------
    "captain_america_bulb": {
        "backend": "tuya",
        "category": "dj",
        "type": "tuya_bulb",
        "id": "405837102cf4325c60c6",
        "room": "bedroom",
        "role": "ambient_light",
        "description": "Captain America ambient bulb",
    },

    "thor_bulb": {
        "backend": "tuya",
        "category": "dj",
        "type": "tuya_bulb",
        "id": "40583710cc50e3e008dd",
        "room": "bedroom",
        "role": "ambient_light",
        "description": "Thor ambient bulb",
    },

    "sky_bulb": {
        "backend": "tuya",
        "category": "dj",
        "type": "tuya_bulb",
        "id": "405837102cf4321d1d05",
        "room": "bedroom",
        "role": "ambient_light",
        "description": "Sky ambient bulb",
    },
}
