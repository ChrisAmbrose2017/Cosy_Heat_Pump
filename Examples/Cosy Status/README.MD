# Octopus Cosy Heat Pump – Python GraphQL Example

This repository contains a **Python example script** demonstrating how to authenticate with the **Octopus Energy GraphQL API** and retrieve data from your **Cosy Heat Pump system**.

The script is intended for **learning, monitoring, and reference purposes only**. It shows how to query:

- Heat pump controller status
- Sensor readings (temperature, humidity)
- Zone setpoints and modes
- Live and lifetime performance metrics (COP, heat output, power input)

⚠️ **Disclaimer:** This is an unofficial example and is not affiliated with Octopus Energy.

---

## 🔐 Security & Privacy

**Important:** The script uses sensitive account information to authenticate. By default, it contains **empty placeholders**, making it safe to share publicly.

```python
email = ""
password = ""
account_id = ""  # A-xxxxxxxx
euid = ""        # Device EUID