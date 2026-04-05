import json
import random
from datetime import datetime, timedelta
import os

# Resolve paths relative to repository root so script works locally and in CI.
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "data")

# Загружаем 10 базовых сюжетов (сохрани JSON выше в base_incidents.json)
with open(os.path.join(DATA_DIR, "base_incidents.json"), "r") as f:
    base_incidents = json.load(f)

PORTS = ["NLRTM", "DEHAM", "BEANR", "GBFXT", "DEBRV", "SGSIN", "MYPKG", "MYTPP", "CNSHA"]
CARGO_TYPES = ["GENERAL", "REEFER", "HAZMAT"]
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

output_dir = os.path.join(DATA_DIR, "batch_incidents_production")
os.makedirs(output_dir, exist_ok=True)

# Сначала сохраняем 10 золотых инцидентов
for i, inc in enumerate(base_incidents):
    with open(f"{output_dir}/incident_{i+1:03d}.json", "w") as f:
        json.dump(inc, f, indent=2)

# Генерируем еще 40 инцидентов на основе золотых шаблонов
start_date = datetime.fromisoformat("2026-05-10T00:00:00Z")

for i in range(11, 51):
    template = random.choice(base_incidents)
    new_port = random.choice(PORTS)
    new_cargo = random.choice(CARGO_TYPES)
    new_teu = random.randint(1500, 18000)
    
    # Модифицируем текст, чтобы он соответствовал новым параметрам, но сохранял физику
    new_text = template["raw_alert_text"].replace(
        template["affected_nodes"][0]["port_code"], new_port
    ).replace(
        str(template["cargo_demand"]["disrupted_teu"]), str(new_teu)
    )
    
    incident = {
        "incident_id": f"INC-2026-{i:03d}-{new_port}-{template['event_type'][:4]}",
        "timestamp": (start_date + timedelta(hours=random.randint(1, 720))).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event_type": template["event_type"],
        "severity_level": template["severity_level"],
        "affected_nodes": [{"port_code": new_port, "impact_type": template["affected_nodes"][0]["impact_type"]}],
        "cargo_demand": {
            "disrupted_teu": new_teu,
            "cargo_type": new_cargo,
            "priority": random.choice(PRIORITIES)
        },
        "estimated_duration_hours": random.choice([24, 48, 72, 96, 120, 168, 240]),
        "raw_alert_text": new_text
    }
    
    with open(f"{output_dir}/incident_{i:03d}.json", "w") as f:
        json.dump(incident, f, indent=2)

print(f"Successfully generated 50 incidents in {output_dir}/")