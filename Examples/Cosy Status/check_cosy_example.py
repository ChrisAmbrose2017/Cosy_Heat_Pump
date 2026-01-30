import requests

# === Your login credentials and device info ===
email = "" # Octopus login email
password = "" # Octopus login password
account_id = "" # Octopus account ID: A-xxxxxxxx
euid = "" # Octopus EUID xxxxxxxxxxxxxxxx

# === GraphQL setup ===
graphql_url = "https://api.octopus.energy/v1/graphql/"
headers = {"Content-Type": "application/json"}

# === Step 1: Get JWT token ===
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

response = requests.post(graphql_url, json={"query": token_query}, headers=headers)
data = response.json()

if "errors" in data:
    print("❌ Failed to get token:")
    print(data)
    exit()

jwt_token = data["data"]["obtainKrakenToken"]["token"]
headers["Authorization"] = f"JWT {jwt_token}"
print("✅ Token retrieved successfully.\n")

# === Step 2: Query status, config, performance ===
status_query = f'''
query {{
  octoHeatPumpControllerStatus(accountNumber: "{account_id}", euid: "{euid}") {{
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
  octoHeatPumpControllerConfiguration(accountNumber: "{account_id}", euid: "{euid}") {{
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
  octoHeatPumpLivePerformance(euid: "{euid}") {{
    coefficientOfPerformance
    outdoorTemperature {{ value unit }}
    heatOutput {{ value unit }}
    powerInput {{ value unit }}
    readAt
  }}
  octoHeatPumpLifetimePerformance(euid: "{euid}") {{
    seasonalCoefficientOfPerformance
    heatOutput {{ value unit }}
    energyInput {{ value unit }}
    readAt
  }}
}}
'''

resp = requests.post(graphql_url, json={"query": status_query}, headers=headers)
result = resp.json()["data"]

# === Helper functions ===
def fmt_temp(t): return f"{t:.1f}°C" if isinstance(t, (float, int)) else "N/A"
def fmt_bool(b): return "✅ Yes" if b else "❌ No"
def fmt_kw(d): return f"{float(d['value']):.2f} {d['unit']}" if d and 'value' in d and 'unit' in d else "N/A"

# === Grouped Output ===

print("🌡️  SENSOR READINGS")
for sensor in result["octoHeatPumpControllerStatus"]["sensors"]:
    code = sensor["code"]
    t = sensor["telemetry"]
    temp = fmt_temp(t["temperatureInCelsius"])
    hum = f"{t['humidityPercentage']}%" if t["humidityPercentage"] is not None else "-"
    print(f"  - {code:8}: {temp:6} | Humidity: {hum:>5}")

print("\n🛠️  CONTROLLER STATUS")
controller = result["octoHeatPumpControllerConfiguration"]["controller"]
print(f"  - State:       {controller['state']}")
print(f"  - Connected:   {fmt_bool(controller['connected'])}")
print(f"  - Timezone:    {controller['heatPumpTimezone']}")

print("\n🔥 ZONE STATUS")
for zone in result["octoHeatPumpControllerStatus"]["zones"]:
    z = zone["telemetry"]
    print(f"  - {zone['zone']:10} | Mode: {z['mode']:>5} | Setpoint: {fmt_temp(z['setpointInCelsius'])} | "
          f"Relay: {fmt_bool(z['relaySwitchedOn'])} | Heat Demand: {fmt_bool(z['heatDemand'])}")

print("\n🧰 HEAT PUMP CONFIGURATION")
hp = result["octoHeatPumpControllerConfiguration"]["heatPump"]
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
print(f"  - WC Allowed Minimum Range:  {fmt_kw(wc['allowableMinimumTemperatureRange']['minimum'])} to {fmt_kw(wc['allowableMinimumTemperatureRange']['maximum'])}")
print(f"  - WC Allowed Maximum Range:  {fmt_kw(wc['allowableMinimumTemperatureRange']['minimum'])} to {fmt_kw(wc['allowableMinimumTemperatureRange']['maximum'])}")

print("\n⚡ LIVE PERFORMANCE")
live = result["octoHeatPumpLivePerformance"]
print(f"  - COP:              {float(live['coefficientOfPerformance']):.2f}")
print(f"  - Outdoor Temp:     {fmt_kw(live['outdoorTemperature'])}")
print(f"  - Heat Output:      {fmt_kw(live['heatOutput'])}")
print(f"  - Power Input:      {fmt_kw(live['powerInput'])}")
print(f"  - Read At:          {live['readAt']}")

print("\n📊 LIFETIME PERFORMANCE")
lifetime = result["octoHeatPumpLifetimePerformance"]
print(f"  - Seasonal COP:     {float(lifetime['seasonalCoefficientOfPerformance']):.2f}")
print(f"  - Total Heat Out:   {fmt_kw(lifetime['heatOutput'])}")
print(f"  - Total Energy In:  {fmt_kw(lifetime['energyInput'])}")
print(f"  - Read At:          {lifetime['readAt']}")
