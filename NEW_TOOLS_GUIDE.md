# New Tools in Infinix v1.6.19

This release adds 8 new tools that significantly expand Infinix's capabilities for network operations and data manipulation.

## Network Tools

### `network.http_request`
Make HTTP requests to any URL with full control over method, headers, and body.

**Parameters:**
- `url` (required): The URL to request (http/https only)
- `method` (optional): HTTP method - GET, POST, PUT, DELETE, or PATCH (default: "GET")
- `headers` (optional): Object with custom HTTP headers
- `body` (optional): Request body as string (for POST/PUT/PATCH)
- `timeout` (optional): Request timeout in seconds (default: 30, max: 300)

**Returns:**
```json
{
  "status_code": 200,
  "headers": {"Content-Type": "application/json", ...},
  "body": "...response body...",
  "elapsed_seconds": 1.234,
  "success": true
}
```

**Example usage:**
```
Use network.http_request to fetch data from https://api.example.com/data
```

**Security:**
- Only http/https schemes allowed
- Response body capped at 1MB
- Full redaction of sensitive headers in event logs

---

### `network.check_port`
Check if a TCP port is open on a host. Useful for service discovery and health checks.

**Parameters:**
- `host` (required): Hostname or IP address
- `port` (required): Port number (1-65535)
- `timeout` (optional): Connection timeout in seconds (default: 5, max: 30)

**Returns:**
```json
{
  "host": "localhost",
  "port": 8080,
  "open": true,
  "elapsed_seconds": 0.012
}
```

**Example usage:**
```
Check if port 3000 is open on localhost using network.check_port
```

---

## Data Transformation Tools

### `data.parse_json`
Parse a JSON string into structured data with error handling.

**Parameters:**
- `text` (required): JSON string to parse

**Returns:**
```json
{
  "parsed": {...parsed object...}
}
```

**Example usage:**
```
Parse this JSON response: {"name": "test", "value": 42}
```

---

### `data.format_json`
Format data as pretty-printed JSON with configurable indentation.

**Parameters:**
- `data` (required): Object to format
- `indent` (optional): Number of spaces for indentation (default: 2, range: 0-8)

**Returns:**
```json
{
  "formatted": "{\n  \"key\": \"value\"\n}"
}
```

**Example usage:**
```
Format this data as readable JSON with 4-space indent
```

---

### `data.parse_csv`
Parse CSV text into a list of dictionaries keyed by column headers.

**Parameters:**
- `text` (required): CSV text to parse
- `delimiter` (optional): Column delimiter (default: ",")

**Returns:**
```json
{
  "rows": [{"Name": "Alice", "Age": "30"}, ...],
  "count": 2
}
```

**Example usage:**
```
Parse this CSV data: Name,Age\nAlice,30\nBob,25
```

---

### `data.format_csv`
Format a list of dictionaries as CSV text with headers.

**Parameters:**
- `data` (required): List of row dictionaries
- `delimiter` (optional): Column delimiter (default: ",")

**Returns:**
```json
{
  "csv": "Name,Age\nAlice,30\nBob,25\n"
}
```

**Example usage:**
```
Convert this data to CSV format: [{"Name": "Alice", "Age": 30}]
```

---

### `data.merge_dicts`
Deep merge two dictionaries. Values from the second dict override the first, with nested dicts merged recursively.

**Parameters:**
- `base` (required): Base dictionary
- `override` (required): Dictionary with values to override/merge

**Returns:**
```json
{
  "merged": {...merged result...}
}
```

**Example usage:**
```
Merge these configs: base={"a": 1, "b": {"x": 1}}, override={"b": {"y": 2}}
Result: {"a": 1, "b": {"x": 1, "y": 2}}
```

---

### `data.flatten_dict`
Flatten a nested dictionary into a single-level dictionary with dot-separated keys.

**Parameters:**
- `dict` (required): Dictionary to flatten
- `sep` (optional): Separator between levels (default: ".")

**Returns:**
```json
{
  "flattened": {"a.b.c": 1, "a.d": 2}
}
```

**Example usage:**
```
Flatten this nested structure: {"user": {"name": "Alice", "age": 30}}
Result: {"user.name": "Alice", "user.age": 30}
```

---

## Capability Profiles

All new tools are subject to the same profile-based access control:

- **Basic profile**: Requires approval for each use
- **Development profile**: Requires approval for each use
- **Broad profile**: Authorized for the session after double-confirmation at startup

Explicit deny rules always take precedence over profile settings.

## Security Considerations

- All network requests are logged with redacted sensitive information
- HTTP responses are capped at 1MB to prevent memory exhaustion
- Only http/https schemes are allowed for network requests
- Port scanning is limited to single port checks (no bulk scanning)
- Event logs redact API keys, tokens, and other secrets automatically

## Use Cases

### API Integration
```python
# Fetch data from an API
result = network.http_request(url="https://api.github.com/users/octocat")
data = data.parse_json(text=result["body"])
print(data["parsed"]["login"])  # octocat
```

### Service Health Check
```python
# Check if your web server is running
port_status = network.check_port(host="localhost", port=8080)
if port_status["open"]:
    print("Server is up!")
```

### Data Processing Pipeline
```python
# Parse, transform, and export data
csv_data = "Name,Score\nAlice,95\nBob,87"
rows = data.parse_csv(text=csv_data)
merged = data.merge_dicts(base={"source": "test"}, override={"count": len(rows["rows"])})
output = data.format_csv(data=rows["rows"])
```

### Configuration Management
```python
# Merge configuration layers
base_config = {"debug": False, "database": {"host": "localhost", "port": 5432}}
override_config = {"database": {"port": 5433}, "logging": True}
final = data.merge_dicts(base=base_config, override=override_config)
# Result: {"debug": False, "database": {"host": "localhost", "port": 5433}, "logging": True}
```

---

For more information, see the CHANGELOG.md and README.md files.
