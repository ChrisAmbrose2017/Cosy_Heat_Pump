# Cosy_Heat_Pump

Unofficial example scripts and reference code for interacting with **Octopus Energy Cosy Heat Pump** systems using the **Octopus GraphQL API**.

This repository is intended as a **learning and reference resource** for developers, hobbyists, and home energy enthusiasts who want to explore heat pump telemetry, configuration, and performance data programmatically.

---

## ⚠️ Disclaimer

This project is **not affiliated with or endorsed by Octopus Energy**.

All scripts in this repository access **private household energy data** when used with real credentials.  
You are responsible for complying with:
- Octopus Energy Terms of Service
- Applicable privacy regulations (e.g. GDPR)

---

## 📦 What’s in this Repo

This repository contains **example scripts** demonstrating how to:

- Authenticate with the Octopus GraphQL API
- Query Cosy Heat Pump controller status
- Read sensor telemetry (temperature, humidity)
- Inspect zone modes and setpoints
- Retrieve live performance metrics (COP, power, heat output)
- Retrieve lifetime / seasonal performance data
- Format and display results in a human-readable way

Scripts are designed to be:
- **Read-only**
- **Well-commented**
- **Easy to adapt**

---

## 🔐 Security & Privacy

All scripts use **placeholders only** by default.

You must provide your own credentials locally:
```python
email = ""
password = ""
account_id = ""  # A-xxxxxxxx
euid = ""        # Device EUID
