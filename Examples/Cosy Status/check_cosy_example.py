import requests
from datetime import datetime, timedelta, timezone

# === Settings ===
VERBOSE = False  # Set to True to show per-period breakdown in performance data

# === Your login credentials and device info ===
email = "" # Octopus login email
password = "" # Octopus login password
account_id = "" # Octopus account ID: A-xxxxxxxx
euid = "" # Octopus EUID xxxxxxxxxxxxxxxx

# === GraphQL setup ===
graphql_url = "https://api.backend.octopus.energy/v1/graphql/"
old_graphql_url = "https://api.octopus.energy/v1/graphql/"

# === Step 1: Get JWT token via old endpoint, used to auth against new endpoint ===
token_query = f'''
mutation {{
  obtainKrakenToken(input: {{
    email: "{email}", 
    password: "{password}"
  }}) {{
    token
  }}
}}
'''

response = requests.post(old_graphql_url, json={"query": token_query}, headers={"Content-Type": "application/json"})
data = response.json()

if "errors" in data:
    print("❌ Failed to get token:")
    print(data)
    exit()

jwt_token = data["data"]["obtainKrakenToken"]["token"]
headers = {
    "Content-Type": "application/json",
    "Authorization": jwt_token,
}
print("✅ Token retrieved successfully.\n")

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
