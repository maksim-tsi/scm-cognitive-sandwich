def get_port_capacities() -> dict[str, int]:
    """
    HTTP client to fetch ground truth from maritime-port-sandbox.
    Provides actual availableCapacityTEU for destination ports.
    
    In a real scenario, this would use the requests library to hit
    the external maritime-port-sandbox API. For now, it returns 
    mocked ground truth data suitable for the IDWL 2026 scenario.
    """
    return {
        "NLRTM": 6000,
        "BEANR": 8000
    }
