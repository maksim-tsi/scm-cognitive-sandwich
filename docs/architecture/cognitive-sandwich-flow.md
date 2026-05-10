# Cognitive Sandwich Architecture: Methodology Flow

This document illustrates the lifecycle of a single scenario routing request within the Cognitive Sandwich architecture, detailing the interaction between the LLM-driven Cognitive Layer and the strict mathematical validation of the Deterministic Layer.

```mermaid
graph TD
    %% Styling Definitions
    classDef cognitive fill:#f3e5f5,stroke:#ab47bc,stroke-width:2px,color:#333
    classDef deterministic fill:#e3f2fd,stroke:#42a5f5,stroke-width:2px,color:#333
    classDef condition fill:#fff3e0,stroke:#ffa726,stroke-width:2px,color:#333
    classDef external fill:#f5f5f5,stroke:#9e9e9e,stroke-width:2px,stroke-dasharray: 5 5,color:#333
    classDef endpoint fill:#e8f5e9,stroke:#66bb6a,stroke-width:2px,color:#333

    Start([Incoming Scenario Routing Request]):::endpoint --> Ingest

    %% Deterministic Layer
    subgraph Deterministic Layer [Deterministic Layer: System State & OR-Solver]
        direction TB
        Ingest[Alert Ingestion<br/>Fetch Port Capacities]:::deterministic
        Sandbox[(Maritime Port Sandbox API)]:::external
        
        Guardrail{Terminal Infeasibility Check<br/>O(1) Pre-flight Guardrail}:::condition
        Solver[OR-Solver Verification<br/>Pyomo Mathematical Validation]:::deterministic
        CheckStatus{Solver Result<br/>Status?}:::condition
        
        Commit[Commit Final State]:::deterministic
    end

    %% Cognitive Layer
    subgraph Cognitive Layer [Cognitive Layer: LLM Operations]
        direction TB
        Draft[State-Aware Prompting<br/>LLM Drafting Artifact v1]:::cognitive
        Repair[IIS-Driven Repair Loop<br/>LLM Repair Artifact vN+1]:::cognitive
    end

    %% Core Data Flow
    Ingest -.->|Query Capacity| Sandbox
    Sandbox -.->|Return Real-Time State| Ingest
    
    Ingest --> Draft
    Draft -->|Proposed Routing Parameters| Guardrail
    
    %% Guardrail logic
    Guardrail -->|Fails: INFEASIBLE (Terminal Deficit)| Commit
    Guardrail -->|Passes O(1) Check| Solver
    
    %% Solver logic
    Solver --> CheckStatus
    CheckStatus -->|FEASIBLE| Commit
    CheckStatus -->|INFEASIBLE<br/>(Yields IIS Conflict Log)| Repair
    
    %% Loop back mechanism
    Repair -->|Revised Routing Parameters| Guardrail
    
    Commit --> End([Exit Workflow]):::endpoint

    %% YAAM Integration mapping
    YAAM[(YAAM Memory Service)]:::external
    Draft -.->|Save Draft| YAAM
    Repair -.->|Attach IIS Feedback & Create Revision| YAAM
    Commit -.->|Consolidate Episode| YAAM
```
