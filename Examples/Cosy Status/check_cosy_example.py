import requests
import json
import os
from datetime import datetime, timedelta, timezone

# === Settings ===
VERBOSE = False  # Set to True to show per-period breakdown in performance data

# === Your Octopus account details ===
# Provide either API key OR email+password.
# API key is available at: https://octopus.energy/dashboard/developer/
api_key = "" # Octopus API key: sk_live_xxxxxxxxxxxxxxxx  (leave blank to use email/password)
email = ""   # Octopus login email    (leave blank if using API key)
password = "" # Octopus login password (leave blank if using API key)
account_id = "" # Octopus account ID: A-xxxxxxxx
euid = "" # Octopus EUID xxxxxxxxxxxxxxxx

# === GraphQL setup ===
graphql_url = "https://api.backend.octopus.energy/v1/graphql/"
old_graphql_url = "https://api.octopus.energy/v1/graphql/"

# === Token cache file (sits alongside this script) ===
TOKEN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_cache.json")

# How many minutes before JWT expiry to proactively refresh (matches Home Assistant behaviour)
TOKEN_REFRESH_BUFFER_MINUTES = 5

# JWT tokens expire after 1 hour; treat cached token as expiring after this long if no expiry stored
JWT_LIFETIME_HOURS = 1


def load_token_cache():
    """Load cached token data from disk. Returns dict or None."""
    if not os.path.exists(TOKEN_CACHE_FILE):
        return None
    try:
        with open(TOKEN_CACHE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_token_cache(token, refresh_token, refresh_expires_in, token_obtained_at):
    """Persist token data to disk."""
    cache = {
        "token": token,
        "refresh_token": refresh_token,
        "refresh_expires_in": refresh_expires_in,  # Unix timestamp (int) from API
        "token_obtained_at": token_obtained_at,     # ISO string (UTC)
    }
    try:
        with open(TOKEN_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except OSError as e:
        print(f"⚠️  Could not save token cache: {e}")


def parse_token_response(data):
    """Extract token fields from a raw obtainKrakenToken response dict."""
    tok = data["data"]["obtainKrakenToken"]
    token = tok["token"]
    refresh_token = tok.get("refreshToken")
    refresh_expires_in = tok.get("refreshExpiresIn")  # Unix timestamp (int)
    return token, refresh_token, refresh_expires_in


def fetch_token_with_credentials():
    """Obtain a fresh JWT using API key (preferred) or email+password. Returns (token, refresh_token, refresh_expires_in) or raises."""
    if api_key:
        input_fields = f'APIKey: "{api_key}"'
        method = "API key"
    elif email and password:
        input_fields = f'email: "{email}", password: "{password}"'
        method = "email/password"
    else:
        raise RuntimeError("No credentials configured: set api_key, or both email and password.")

    query = f'''
mutation {{
  obtainKrakenToken(input: {{
    {input_fields}
  }}) {{
    token
    refreshToken
    refreshExpiresIn
  }}
}}
'''
    response = requests.post(
        old_graphql_url,
        json={"query": query},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    data = response.json()
    if "errors" in data:
        raise RuntimeError(f"Auth error ({method}): {data['errors']}")
    return parse_token_response(data)


def fetch_token_with_refresh(refresh_token):
    """Obtain a fresh JWT using an existing refresh token. Returns (token, refresh_token, refresh_expires_in) or raises."""
    query = f'''
mutation {{
  obtainKrakenToken(input: {{
    refreshToken: "{refresh_token}"
  }}) {{
    token
    refreshToken
    refreshExpiresIn
  }}
}}
'''
    response = requests.post(
        old_graphql_url,
        json={"query": query},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    data = response.json()
    if "errors" in data:
        raise RuntimeError(f"Refresh error: {data['errors']}")
    return parse_token_response(data)


def get_valid_token():
    """
    Return a valid JWT, using the cache where possible.
    Strategy (mirrors Home Assistant OctopusEnergy integration):
      1. If cached JWT is still valid (with TOKEN_REFRESH_BUFFER_MINUTES buffer), use it.
      2. If JWT is expiring soon but refresh token is still valid, silently refresh using it.
      3. If refresh token is also expired, fall back to API key.
      4. If the server is unreachable for (2) or (3), use the stale cached JWT with a warning
         rather than failing completely.
    """
    now = datetime.now(timezone.utc)
    cache = load_token_cache()

    if cache:
        # Determine when the cached JWT expires
        obtained_at = datetime.fromisoformat(cache["token_obtained_at"])
        jwt_expires_at = obtained_at + timedelta(hours=JWT_LIFETIME_HOURS)
        token_still_good = (jwt_expires_at - timedelta(minutes=TOKEN_REFRESH_BUFFER_MINUTES)) > now

        if token_still_good:
            print("✅ Using cached token (still valid).\n")
            return cache["token"]

        # JWT is expiring — try refresh token first
        refresh_token = cache.get("refresh_token")
        refresh_expires_in = cache.get("refresh_expires_in")
        refresh_still_good = (
            refresh_token is not None
            and refresh_expires_in is not None
            and datetime.fromtimestamp(refresh_expires_in, tz=timezone.utc) > now
        )

        if refresh_still_good:
            try:
                print("🔄 JWT expiring — refreshing via refresh token...")
                token, new_refresh_token, new_refresh_expires_in = fetch_token_with_refresh(refresh_token)
                save_token_cache(token, new_refresh_token, new_refresh_expires_in, now.isoformat())
                print("✅ Token refreshed successfully.\n")
                return token
            except Exception as e:
                print(f"⚠️  Refresh token failed ({e}), falling back to credentials...")

        # Refresh token expired or refresh failed — try full login
        try:
            print("🔑 Re-authenticating with credentials...")
            token, new_refresh_token, new_refresh_expires_in = fetch_token_with_credentials()
            save_token_cache(token, new_refresh_token, new_refresh_expires_in, now.isoformat())
            print("✅ Token retrieved successfully.\n")
            return token
        except Exception as e:
            # Server unreachable — use stale token as a last resort
            if cache.get("token"):
                print(f"⚠️  Server unreachable ({e}). Using stale cached token — results may be outdated.\n")
                return cache["token"]
            raise RuntimeError(f"Cannot obtain a token and no cached token available: {e}") from e

    # No cache at all — must authenticate from scratch
    try:
        print("🔑 No cached token found — authenticating with credentials...")
        token, refresh_token, refresh_expires_in = fetch_token_with_credentials()
        save_token_cache(token, refresh_token, refresh_expires_in, now.isoformat())
        print("✅ Token retrieved successfully.\n")
        return token
    except Exception as e:
        raise RuntimeError(f"Cannot obtain a token: {e}") from e


# === Step 1: Get a valid JWT (from cache or fresh login) ===
jwt_token = get_valid_token()
headers = {
    "Content-Type": "application/json",
    "Authorization": jwt_token,
}

# === Step 2: Query status, config, lifetime performance ===
status_query = f'''
query {{
  heatPumpControllerStatus(accountNumber: "{account_id}", euid: "{euid}") {{
    sensors {{
      code
      telemetry {{
        temperatureInCelsius
        humidityPercentage
        retrievedAt
      }}
    }}
    zones {{
      zone 
      telemetry {{
        setpointInCelsius
        mode
        relaySwitchedOn
        heatDemand
        retrievedAt
      }}
    }}
  }}
  heatPumpControllerConfiguration(accountNumber: "{account_id}", euid: "{euid}") {{
    controller {{
      state
      heatPumpTimezone
      connected
    }}
    heatPump {{
      serialNumber
      model
      hardwareVersion
      faultCodes
      maxWaterSetpoint
      minWaterSetpoint
      heatingFlowTemperature {{
        currentTemperature {{ value unit }}
        allowableRange {{
          minimum {{ value unit }}
          maximum {{ value unit }}
        }}
      }}
      weatherCompensation {{
        enabled
        currentRange {{
          minimum {{ value unit }}
          maximum {{ value unit }}
        }}
        allowableMinimumTemperatureRange  {{
          minimum {{ value unit }}
          maximum {{ value unit }}
        }}
        allowableMaximumTemperatureRange  {{
          minimum {{ value unit }}
          maximum {{ value unit }}
        }}
      }}
    }}
  }}
  heatPumpLifetimePerformance(accountNumber: "{account_id}", euid: "{euid}") {{
    seasonalCoefficientOfPerformance
    heatOutput {{ value unit }}
    energyInput {{ value unit }}
    readAt
  }}
  heatPumpLivePerformance(accountNumber: "{account_id}", euid: "{euid}") {{
    readAt
    coefficientOfPerformance
    powerInput {{ value unit }}
    heatOutput {{ value unit }}
    outdoorTemperature {{ value unit }}
  }}
}}
'''

resp = requests.post(graphql_url, json={"query": status_query}, headers=headers)
result = resp.json()["data"]

# === Step 2B: Query time series performance (LIVE, DAY, WEEK, MONTH) ===

now = datetime.now(timezone.utc)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

time_ranges = {
    "LIVE":  {"start": now - timedelta(minutes=5), "end": now, "grouping": "LIVE"},
    "Today": {"start": today_start,                "end": now, "grouping": "DAY"},
    "Last Week":  {"start": now - timedelta(weeks=1), "end": now, "grouping": "WEEK"},
    "Last Month": {"start": now - timedelta(days=30), "end": now, "grouping": "MONTH"},
}

perf_results = {}
for label, r in time_ranges.items():
    start_str = r["start"].strftime("%Y-%m-%dT%H:%M:%S+0000")
    end_str = r["end"].strftime("%Y-%m-%dT%H:%M:%S+0000")
    
    query = f'''
    query {{
      heatPumpTimeSeriesPerformance(
        accountNumber: "{account_id}",
        euid: "{euid}",
        startAt: "{start_str}",
        endAt: "{end_str}",
        performanceGrouping: {r["grouping"]}
      ) {{
        startAt
        endAt
        energyInput {{ value unit }}
        energyOutput {{ value unit }}
        outdoorTemperature {{ value unit }}
      }}
    }}
    '''
    
    resp_perf = requests.post(graphql_url, json={"query": query}, headers=headers)
    data_perf = resp_perf.json()
    
    if "errors" in data_perf:
        print(f"  ⚠️ {label}: Failed - {data_perf['errors'][0].get('message', 'Unknown')}")
        perf_results[label] = None
    else:
        nodes = data_perf["data"]["heatPumpTimeSeriesPerformance"]
        perf_results[label] = nodes if nodes else None

# === Helper functions ===
def fmt_temp(t): return f"{t:.1f}°C" if isinstance(t, (float, int)) else "N/A"
def fmt_bool(b): return "✅ Yes" if b else "❌ No"
def fmt_kw(d): return f"{float(d['value']):.2f} {d['unit']}" if d and 'value' in d and 'unit' in d else "N/A"

# === Grouped Output ===

print("🌡️  SENSOR READINGS")
for sensor in result["heatPumpControllerStatus"]["sensors"]:
    code = sensor["code"]
    t = sensor["telemetry"]
    temp = fmt_temp(t["temperatureInCelsius"])
    hum = f"{t['humidityPercentage']}%" if t["humidityPercentage"] is not None else "-"
    print(f"  - {code:8}: {temp:6} | Humidity: {hum:>5}")

print("\n🛠️  CONTROLLER STATUS")
controller = result["heatPumpControllerConfiguration"]["controller"]
print(f"  - State:       {controller['state']}")
print(f"  - Connected:   {fmt_bool(controller['connected'])}")
print(f"  - Timezone:    {controller['heatPumpTimezone']}")

print("\n🔥 ZONE STATUS")
for zone in result["heatPumpControllerStatus"]["zones"]:
    z = zone["telemetry"]
    print(f"  - {zone['zone']:10} | Mode: {z['mode']:>5} | Setpoint: {fmt_temp(z['setpointInCelsius'])} | "
          f"Relay: {fmt_bool(z['relaySwitchedOn'])} | Heat Demand: {fmt_bool(z['heatDemand'])}")

print("\n🧰 HEAT PUMP CONFIGURATION")
hp = result["heatPumpControllerConfiguration"]["heatPump"]
print(f"  - Model:        {hp['model']}")
print(f"  - Serial:       {hp['serialNumber']}")
print(f"  - HW Version:   {hp['hardwareVersion']}")
print(f"  - Fault Codes:  {hp['faultCodes'] or 'None'}")
print(f"  - Max Setpoint: {fmt_temp(hp['maxWaterSetpoint'])}")
print(f"  - Min Setpoint: {fmt_temp(hp['minWaterSetpoint'])}")
hft = hp['heatingFlowTemperature']
print(f"  - Current Flow Temp: {fmt_kw(hft['currentTemperature'])}")
print(f"  - Flow Temp Range:   {fmt_kw(hft['allowableRange']['minimum'])} to {fmt_kw(hft['allowableRange']['maximum'])}")

wc = hp['weatherCompensation']
print(f"  - Weather Comp: {fmt_bool(wc['enabled'])}")
print(f"  - WC Current Range:  {fmt_kw(wc['currentRange']['minimum'])} to {fmt_kw(wc['currentRange']['maximum'])}")
print(f"  - WC Allowed Range:  {fmt_kw(wc['allowableMinimumTemperatureRange']['minimum'])} to {fmt_kw(wc['allowableMaximumTemperatureRange']['maximum'])}")

print("\n⚡ PERFORMANCE (Time Series)")
for label, nodes in perf_results.items():
    print(f"\n  📌 {label}:")
    if not nodes:
        print("     ⚠️ No data available")
        continue
    
    if label == "LIVE":
        # LIVE grouping returns outdoor temperature only — energy values are not available
        print(f"     - ({len(nodes)} data points in last 5 min)")
        for i, entry in enumerate(nodes):
            print(f"       [{i+1}] Outdoor: {fmt_kw(entry.get('outdoorTemperature'))} | Read At: {entry['startAt']}")
        # COP and energy derived from last Today (DAY) hourly bucket
        today_nodes = perf_results.get("Today")
        if today_nodes:
            latest_day = today_nodes[-1]
            e_in = float(latest_day['energyInput']['value']) if latest_day.get('energyInput') else 0
            e_out = float(latest_day['energyOutput']['value']) if latest_day.get('energyOutput') else 0
            cop = e_out / e_in if e_in > 0 else 0
            print(f"     - COP (current hour):   {cop:.2f}  [{latest_day['startAt']} → {latest_day['endAt']}]")
            print(f"     - Energy Output:        {fmt_kw(latest_day.get('energyOutput'))}")
            print(f"     - Energy Input:         {fmt_kw(latest_day.get('energyInput'))}")
        else:
            print("     ⚠️ No Today data available for COP")
    else:
        total_in = 0
        total_out = 0
        for node in nodes:
            e_in = float(node['energyInput']['value']) if node.get('energyInput') else 0
            e_out = float(node['energyOutput']['value']) if node.get('energyOutput') else 0
            total_in += e_in
            total_out += e_out
        
        avg_cop = total_out / total_in if total_in > 0 else 0
        print(f"     - Periods:          {len(nodes)}")
        print(f"     - Total Energy In:  {total_in:.2f} kWh")
        print(f"     - Total Energy Out: {total_out:.2f} kWh")
        print(f"     - Avg COP:          {avg_cop:.2f}")
        
        if VERBOSE:
            for node in nodes:
                e_in = float(node['energyInput']['value']) if node.get('energyInput') else 0
                e_out = float(node['energyOutput']['value']) if node.get('energyOutput') else 0
                node_cop = e_out / e_in if e_in > 0 else 0
                outdoor = fmt_kw(node.get('outdoorTemperature'))
                print(f"       {node['startAt']} → {node['endAt']}  |  In: {e_in:.2f}  Out: {e_out:.2f}  COP: {node_cop:.2f}  Outdoor: {outdoor}")

print("\n⚡ LIVE PERFORMANCE")
live = result["heatPumpLivePerformance"]
if live:
    cop_live = float(live['coefficientOfPerformance']) if live.get('coefficientOfPerformance') is not None else None
    cop_str = f"{cop_live:.2f}" if cop_live is not None else "N/A"
    print(f"  - COP:              {cop_str}")
    print(f"  - Power Input:      {fmt_kw(live.get('powerInput'))}")
    print(f"  - Heat Output:      {fmt_kw(live.get('heatOutput'))}")
    print(f"  - Outdoor Temp:     {fmt_kw(live.get('outdoorTemperature'))}")
    print(f"  - Read At:          {live['readAt']}")
else:
    print("  ⚠️ No live data available")

print("\n📊 LIFETIME PERFORMANCE")
lifetime = result["heatPumpLifetimePerformance"]
print(f"  - Seasonal COP:     {float(lifetime['seasonalCoefficientOfPerformance']):.2f}")
print(f"  - Total Heat Out:   {fmt_kw(lifetime['heatOutput'])}")
print(f"  - Total Energy In:  {fmt_kw(lifetime['energyInput'])}")
print(f"  - Read At:          {lifetime['readAt']}")
