import httpx

def get_port_capacities(ports: list[str] = None) -> dict[str, int]:
    """
    HTTP client to fetch ground truth from maritime-port-sandbox.
    Provides actual availableCapacityTEU for destination ports.
    """
    if ports is None:
        ports = ["NLRTM", "BEANR"]
        
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
