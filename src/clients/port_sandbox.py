import os
import httpx

def get_port_capacities(ports: list[str] | None = None) -> dict[str, int]:
    """
    HTTP client to fetch ground truth from maritime-port-sandbox.
    Provides actual availableCapacityTEU for destination ports.
    """
    use_mock = os.getenv("USE_MOCK_SANDBOX", "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if use_mock:
        mock_capacities: dict[str, int] = {
            "NLRTM": 25000,
            "BEANR": 15000,
            "DEBRV": 10000,
        }
        if ports is None:
            return dict(mock_capacities)
        return {port: mock_capacities.get(port, 0) for port in ports}

    if ports is None:
        ports = ["NLRTM", "BEANR", "DEBRV"]
        
    capacities = {}
    with httpx.Client() as client:
        for port in ports:
            url = f"http://localhost:8000/api/v1/pcs/terminals/{port}/status"
            try:
                response = client.get(url, timeout=5.0)
                response.raise_for_status()
                data = response.json()
                capacities[port] = data.get("availableCapacityTEU", 0)
            except Exception as e:
                print(f"[Port Sandbox] Error fetching {port}: {e}")
                capacities[port] = 0
                
    return capacities
