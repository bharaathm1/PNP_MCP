# PPM Constraints Reference

## Overview
Power Performance Manager (PPM) validation constraints for SOCWatch analysis. These constraints validate workload classification, containment policy, hetero scheduling, and core unpark behavior.

## Purpose
Automated validation of power management behavior during ETL trace analysis to ensure system operates within expected parameters for power efficiency.

## Constraint Categories

### 1. Workload Classification (WLC)

#### Bursty WLC Check
- **Condition**: `wlc_3 < 5`
- **Expected**: Bursty residency should be minimal
- **Action Required**: System seems to be more bursty than usual, this will lead to power regression
- **Interpretation**: High bursty workload indicates frequent transitions that increase power consumption

#### BL WLC Check  
- **Condition**: `wlc_1 > 95`
- **Expected**: Baseline (BL) residency should dominate
- **Action Required**: System seems to be less BL classified than expected, this will lead to power regression
- **Interpretation**: Low baseline residency means workload not staying in lowest power state

### 2. Containment Policy

#### Containment Enabled Check
- **Condition**: `CE_1 == 100`
- **Expected**: Containment should be enabled 100% of time
- **Action Required**: Containment seems to be disabled during the workload
- **Interpretation**: Containment policy keeps workload on minimal cores for power efficiency

#### Containment Crossover Check
- **Condition**: `CCR_1 > 10`
- **Expected**: Containment crossover should be rare (< 10%)
- **Action Required**: Containment crossover is happening more frequently than usual, this can lead to containment breach and power regression
- **Interpretation**: Frequent crossover indicates workload exceeds containment capacity

### 3. Heterogeneous Scheduling

#### Hetero Policy Check
- **Condition**: `HP_4 == 100`
- **Expected**: Hetero policy should be enabled
- **Action Required**: Hetero policy is disabled on this system, scheduling will use P-core first
- **Interpretation**: Without hetero policy, scheduler doesn't optimize P-core vs E-core selection

#### Hetero Containment Policy - Efficiency Zone
- **Condition**: `HCP_0 == 100`
- **Expected**: Should operate in efficiency zone 100% of time
- **Action Required**: We are not working in Hetero containment policy eff zone
- **Interpretation**: Efficiency zone prioritizes E-cores for best power efficiency

#### Hetero Containment Policy - Hybrid Zone
- **Condition**: `HCP_1 == 100`
- **Expected**: Should operate in hybrid zone 100% of time
- **Action Required**: We are not working in Hetero containment policy hybrid zone
- **Interpretation**: Hybrid zone balances P-core and E-core usage

### 4. Core Unpark Counts

#### Total Core Unpark Thresholds
| Unpark Count | Threshold | Condition | Action Required |
|-------------|-----------|-----------|-----------------|
| TCU_1 | < 10% | Low unpark count acceptable | Total core unpark count is high |
| TCU_2 | > 40% | Medium unpark should dominate | Total core unpark count is high |
| TCU_3 | > 40% | Medium-high unpark should dominate | Total core unpark count is high |
| TCU_4 | < 10% | High unpark count should be rare | Total core unpark count is high |
| TCU_5 | < 10% | Very high unpark should be rare | Total core unpark count is high |

**Interpretation**: 
- Lower unpark counts (1-2 cores) indicate better power efficiency
- Higher unpark counts (4-5+ cores) indicate more parallelism but higher power
- Ideal workload should primarily stay in TCU_2 and TCU_3 range

#### P-core Unpark Count
- **Condition**: `PCU_0 > 90`
- **Expected**: Zero P-cores unparked most of the time (> 90%)
- **Action Required**: Total P-core unpark count is high
- **Interpretation**: More P-core usage means higher power consumption; E-cores preferred for efficiency

## Constraint Format

Each constraint follows this structure:
```
CONSTRAINT(
    NAME="<Descriptive name>",
    CATEGORY="SOCWatch",
    CONDITION=<Boolean expression>,
    MESSAGE="<What is being checked>",
    AR="<Action required if constraint fails>"
)
```

## Usage in Analysis

### How Constraints Are Evaluated
1. ETL trace analyzed to extract SOCWatch metrics
2. Each constraint's CONDITION evaluated against extracted values
3. Failed constraints trigger AR (Action Required) message
4. Results reported in validation summary

### Constraint Status Meanings
- ✅ **PASS**: Condition met, system behaving as expected
- ❌ **FAIL**: Condition violated, action required
- ⚠️ **WARNING**: Near threshold, monitor closely

## Common Failure Scenarios

### Power Regression Indicators
1. **High Bursty WLC**: System not staying in stable states
2. **Low BL WLC**: Not enough time in lowest power state
3. **Containment Disabled**: Cores not being constrained
4. **High Crossover**: Workload exceeding containment capacity
5. **High P-core Usage**: Using performance cores when efficiency cores sufficient

### Performance Issues
1. **Hetero Policy Disabled**: P-core preference may cause power waste
2. **Wrong Containment Zone**: Not optimizing for efficiency
3. **Excessive Unpark Counts**: Thrashing between core states

## Validation Workflow

```
ETL Trace
    ↓
Extract SOCWatch Metrics
    ↓
Evaluate Constraints
    ↓
Generate Pass/Fail Report
    ↓
If FAIL → Check AR field
    ↓
Investigate root cause
    ↓
Apply recommended action
```

## Related Constraints
- [PPM Settings Constraints](constraints_ppm_val.md) - Detailed PPM parameter validation
- [Teams Constraints](constraints_teams.md) - Teams workload-specific validation
- [Constraints Validation](constraints_validation.md) - General constraint framework

## Related Analyses
- WLC Workload Classification
- Hetero Response
- Containment Policy
- WPS Containment Unpark
- PPM Settings

## Debugging Tips

### Issue: Power Regression
```python
# Check WLC distribution
wlc_df[wlc_df['wlc'] == 1]['duration'].sum() / total_duration
# Should be > 95% for BL workload

# Check containment enabled
containment_df['ContainmentEnabled'].mean()
# Should be 1.0 (100%)
```

### Issue: Performance Problems
```python
# Check hetero policy
hetero_policy_enabled = hp_df[hp_df['policy'] == 4]['duration'].sum()
# Should cover entire trace

# Check unpark distribution
unpark_counts = tcu_df['count'].value_counts()
# Should concentrate in 2-3 core range
```

## Implementation Location
- **Constraint File**: `speedlibs_service/constraints/PPM_constraint.txt`
- **Validation Module**: Part of ETL analysis comprehensive validation
- **Related Code**: `speedlibs_service/speedlibs_clean.py` - EtlTrace class methods
