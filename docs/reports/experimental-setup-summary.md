# Experimental Setup Summary

| Parameter | Configuration / Value | Details / Mathematical Constraint |
| :--- | :--- | :--- |
| **Total Scenarios** | 100 | Number of procedurally generated routing requests in the current dataset (`scenarios_idwl_v1.csv`). |
| **Target Topology** | NLRTM, BEANR, DEHAM, DEBRV | The Northern European port nodes allowed for rerouting allocations. |
| **Cargo Volume Range** | 5,000 – 50,000 TEU | The range of randomly sampled cargo volumes (TEU) that must be rerouted per scenario. |
| **Degradation: Total Closure** | 0% Capacity Constraint | Simulates complete operational suspension (e.g., 48-hour labor strikes). |
| **Degradation: Operational Restriction**| 50% Capacity Constraint | Simulates partial capacity reduction (e.g., STS cranes offline for emergency repair). |
| **Degradation: Severe Congestion** | 20% Capacity Constraint | Simulates extreme yard utilization (92%), capping throughput to prevent gridlock. |
