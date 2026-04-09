# Soft Park Selection Module

Tracks soft parking decisions (logical parking without full power down) for fine-grained power management.

## Data Source
- **Provider**: Microsoft-Windows-Kernel-Processor-Power/SoftParkSelection
- **Fields**: OldPark, NewPark, NewSoftPark (hex bitmasks converted to binary)

## Output Format
- timestamp, OldPark, NewPark, NewSoftPark (binary strings showing core parking state)

## What It Shows
- Soft parking allows cores to stay responsive while saving power
- Binary bitmasks show which cores are parked/unparked
- Transitions between parking states over time

## Implementation
- Module: speedlibs_clean.py, Class: EtlTrace, Method: softparkselection()
