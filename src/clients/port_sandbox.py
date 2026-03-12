import os
import httpx

MOCK_CAPACITIES: dict[str, int] = {
    "NLRTM": 25000,
    "BEANR": 15000,
    "DEBRV": 10000,
}

def get_port_capacities(ports: list[str] | None = None) -> dict[str, int]:
    """
    HTTP client to fetch ground truth from maritime-port-sandbox.
    Provides actual availableCapacityTEU for destination ports.
    """
    use_mock = os.getenv("USE_MOCK_SANDBOX", "").strip().lower() == "true"
    if use_mock:
        if ports is None:
            return dict(MOCK_CAPACITIES)
        return {port: MOCK_CAPACITIES.get(port, 0) for port in ports}

    if ports is None:
        ports = ["NLRTM", "BEANR", "DEBRV"]
        
    base_url = os.getenv("SANDBOX_API_URL", "http://localhost:8000").rstrip("/")
    capacities = {}
    with httpx.Client() as client:
        for port in ports:
            url = f"{base_url}/api/v1/pcs/terminals/{port}/status"
            try:
                response = client.get(url, timeout=5.0)
                response.raise_for_status()
                data = response.json()
                capacities[port] = data.get("availableCapacityTEU", 0)
            except Exception as e:
                print(f"[Port Sandbox] Error fetching {port} from {url}: {e}")
                if port in MOCK_CAPACITIES:
                    capacities[port] = MOCK_CAPACITIES[port]
                else:
                    raise RuntimeError(
                        f"Port sandbox request failed for unknown port {port} ({url})"
                    ) from e
                
    return capacities
