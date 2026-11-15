import requests
import config

PPE_NAMES = {
    "helmet": "helmet",
    "glasses": "safety glasses",
    "hivis": "hi-vis vest",
    "shoes": "closed shoes",
    "mask": "face mask",
}

HAZARD_NAMES = {
    "tripping": "tripping hazard",
    "electrical": "electrical hazard",
    "temperature": "temperature hazard",
}

# Calls ppe workflow and returns image data
def call_ppe() -> dict:
    resp = requests.post(config.PPE_URL, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) else data

def call_hazards() -> dict:
    resp = requests.post(config.HAZARD_URL, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) else data

def call_checks() -> dict:
    resp = requests.post(config.CHECKS_URL, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) else data

def call_report(ppe: dict, hazards: dict, timestamp: str) -> dict:
    resp = requests.post(config.REPORT_URL, json={
        "ppe": ppe,
        "hazards": hazards,
        "timestamp": timestamp,
    }, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) else data