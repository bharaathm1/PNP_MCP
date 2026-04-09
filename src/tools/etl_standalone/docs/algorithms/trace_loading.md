# Trace Loading and Caching Logic

## Overview
Intelligent trace loading system with automatic caching to avoid repeatedly loading the same large ETL files, significantly improving analysis performance.

## Analysis Type
**ETL Trace Loading with Cache Management**

## What It Does
- Loads ETL trace files using SPEED kernel
- Caches loaded traces in memory
- Automatically reuses cached traces
- Manages cache size and TTL (Time-To-Live)
- Invalidates cache on file modification

## Cache Strategy

### Cache Key Components:
```python
cache_key = f"{abs_path}:{file_mtime}:{time_range}:{fast_mode}:{kwargs}"
```

| Component | Purpose |
|-----------|---------|
| `abs_path` | Absolute file path (unique identifier) |
| `file_mtime` | File modification time (detects changes) |
| `time_range` | Time window for analysis |
| `fast_mode` | Fast loading flag |
| `kwargs` | Additional parameters (e.g., socwatch_file) |

### Cache Management Parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `_CACHE_MAX_SIZE` | 5 | Maximum traces to keep in memory |
| `_CACHE_MAX_AGE_SECONDS` | 1800 | 30 minutes TTL |
| Eviction Strategy | LRU | Least Recently Used |

## Loading Process

### Step 1: Check Cache
```python
if cache_key in _TRACE_CACHE and not force_reload:
    cached_trace, cache_time = _TRACE_CACHE[cache_key]
    
    # Check TTL
    age = current_time - cache_time
    if age < _CACHE_MAX_AGE_SECONDS:
        return cached_trace  # Cache hit!
```

### Step 2: Load from File (Cache Miss)
```python
# Load using SPEED kernel
trace = load_trace(
    etl_file=etl_file,
    time_range=time_range,
    **kwargs
)
```

### Step 3: Store in Cache
```python
# Add to cache with timestamp
_TRACE_CACHE[cache_key] = (trace, current_time)

# Evict old entries if cache is full
if len(_TRACE_CACHE) > _CACHE_MAX_SIZE:
    evict_oldest_entry()
```

### Step 4: Return Trace
```python
return trace
```

## Performance Benefits

### Without Caching:
```
First load:  ~20s for 1GB file
Second load: ~20s (reloads from disk)
Third load:  ~20s (reloads from disk)
Total:       ~60s for 3 analyses
```

### With Caching:
```
First load:  ~20s for 1GB file (cache miss)
Second load: ~0.1s (cache hit!)
Third load:  ~0.1s (cache hit!)
Total:       ~20.2s for 3 analyses (200x faster for subsequent loads!)
```

## Cache Invalidation

### Automatic Invalidation:
1. **File Modification**: Cache key includes `mtime`, so modified files get new key
2. **TTL Expiry**: Entries older than 30 minutes are invalidated
3. **Cache Full**: LRU eviction removes least recently used
4. **Force Reload**: `force_reload=True` bypasses cache

### Manual Invalidation:
```python
# Clear entire cache
clear_trace_cache()

# Get cache statistics
stats = get_trace_cache_stats()
```

## Function Signature

```python
def load_trace_cached(
    etl_file: str,
    time_range: tuple = None,
    fast_mode: bool = False,
    force_reload: bool = False,
    **kwargs
) -> Trace:
    """
    Load ETL trace with automatic caching
    
    Args:
        etl_file: Path to ETL file
        time_range: Optional time window (start_sec, end_sec)
        fast_mode: Use fast loading mode
        force_reload: Bypass cache and force reload
        **kwargs: Additional parameters (e.g., socwatch_summary_file)
    
    Returns:
        Trace object from SPEED kernel
    """
```

## Supported Additional Parameters

### SocWatch Integration:
```python
trace = load_trace_cached(
    etl_file="path/to/file.etl",
    socwatch_summary_file="path/to/socwatch.csv"
)
```

### Time Range Filtering:
```python
trace = load_trace_cached(
    etl_file="path/to/file.etl",
    time_range=(10, 60)  # Analyze 10-60 seconds only
)
```

### Fast Mode:
```python
trace = load_trace_cached(
    etl_file="path/to/file.etl",
    fast_mode=True  # Skip some processing for speed
)
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Function**: `load_trace_cached()`
- **Lines**: Approximately 60-150
- **Global Variables**: `_TRACE_CACHE`, `_CACHE_MAX_SIZE`, `_CACHE_MAX_AGE_SECONDS`

## Cache Statistics

### Get Cache Info:
```python
stats = get_trace_cache_stats()

print(f"Cached traces: {stats['count']}")
print(f"Cache keys: {stats['keys']}")
print(f"Max size: {stats['max_size']}")
print(f"Max age: {stats['max_age_seconds']}s")
```

### Clear Cache:
```python
clear_trace_cache()
print("Cache cleared!")
```

## Usage in Analysis Functions

### Teams KPI Analysis:
```python
def teams_KPI_analysis(etl_path, ...):
    # Load once, use for multiple analyses
    trace = load_trace_cached(etl_file=etl_path, time_range=time_range)
    
    # VCIP uses same trace
    vcip_result = vcip_analyzer.analyze_4ip_alignment(
        etl_path_or_trace=trace,  # Pass cached trace object!
        time_range=vcip_time_range
    )
    
    # FPS uses same trace
    fps_result = fps_analyzer.analyze_fps(
        etl_path_or_trace=trace,  # Reuse cached trace!
        time_range=fps_time_range
    )
```

### Comprehensive Analysis:
```python
def generate_comprehensive_analysis(etl_path, ...):
    # Load with cache
    trace = load_trace_cached(
        etl_file=etl_path,
        time_range=time_range,
        socwatch_summary_file=socwatch_file
    )
    
    # All subsequent operations use cached trace
    combined_df = extract_combined_dataframe(trace)
    hetero_df = extract_hetero_response(trace)
    containment_df = analyze_containment(trace)
```

## Memory Considerations

### Trace Size in Memory:
- Typical 1GB ETL file → ~500MB-1GB in memory
- 5 cached traces → ~2.5GB-5GB RAM usage
- Adjust `_CACHE_MAX_SIZE` based on available RAM

### Recommendations:
- **16GB RAM**: `_CACHE_MAX_SIZE = 5` (default)
- **8GB RAM**: `_CACHE_MAX_SIZE = 2-3`
- **32GB+ RAM**: `_CACHE_MAX_SIZE = 10+`

## Cache Behavior Examples

### Example 1: Same File, Different Time Ranges
```python
# First call - cache miss
trace1 = load_trace_cached(file, time_range=(0, 60))  # ~20s

# Second call - DIFFERENT cache key (different time_range)
trace2 = load_trace_cached(file, time_range=(10, 70))  # ~20s (cache miss)
```

### Example 2: Same File, Same Parameters
```python
# First call - cache miss
trace1 = load_trace_cached(file, time_range=(0, 60))  # ~20s

# Second call - SAME cache key
trace2 = load_trace_cached(file, time_range=(0, 60))  # ~0.1s (cache hit!)
```

### Example 3: File Modified
```python
# First call
trace1 = load_trace_cached("file.etl")  # ~20s

# File is modified externally
# modify_file("file.etl")

# Second call - cache miss (mtime changed)
trace2 = load_trace_cached("file.etl")  # ~20s (new cache key)
```

## Best Practices

### 1. Reuse Trace Objects
```python
# GOOD - Pass trace object to multiple analyzers
trace = load_trace_cached(etl_path)
fps_result = analyze_fps(trace)
vcip_result = analyze_vcip(trace)

# BAD - Reload same file multiple times
fps_result = analyze_fps(etl_path)  # Loads file
vcip_result = analyze_vcip(etl_path)  # Reloads same file
```

### 2. Use Consistent Time Ranges
```python
# GOOD - Same time_range gets cache hit
main_range = (0, 60)
trace = load_trace_cached(file, time_range=main_range)
# Subsequent calls with main_range will hit cache

# LESS EFFICIENT - Different time ranges create separate cache entries
trace1 = load_trace_cached(file, time_range=(0, 60))
trace2 = load_trace_cached(file, time_range=(5, 65))  # Different cache entry
```

### 3. Clear Cache When Done
```python
# After batch processing
for etl_file in etl_files:
    analyze_file(etl_file)

# Clear cache to free memory
clear_trace_cache()
```

## Related Functions
- `clear_trace_cache()`: Clear all cached traces
- `get_trace_cache_stats()`: Get cache statistics
- `load_trace()`: Original uncached loader (SPEED kernel)
