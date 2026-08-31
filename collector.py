import os
import csv
from datetime import datetime
import requests

# Retrieve API keys from GitHub Secrets
GOOGLE_MAPS_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
OPENWEATHER_KEY = os.environ.get('OPENWEATHER_API_KEY')

# Standardized 7-8 km Srinagar Traffic Corridors
CORRIDORS = [
    {"id": 1, "name": "Lal Chowk to Hyderpora", "origin": "Lal Chowk, Srinagar", "destination": "Hyderpora, Srinagar"},
    {"id": 2, "name": "Dalgate to Pantha Chowk", "origin": "Dalgate, Srinagar", "destination": "Pantha Chowk, Srinagar"},
    {"id": 3, "name": "Jahangir Chowk to Parimpora", "origin": "Jahangir Chowk, Srinagar", "destination": "Parimpora, Srinagar"}
]

# File where dataset will be logged
CSV_FILE = "traffic_data.csv"

def get_weather():
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Srinagar,IN&appid={OPENWEATHER_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=10).json()
        if response.get("cod") == 200:
            return {
                "temp": response["main"]["temp"],
                "humidity": response["main"]["humidity"],
                "weather_main": response["weather"][0]["main"],
                "rain_1h": response.get("rain", {}).get("1h", 0)
            }
    except Exception as e:
        print(f"Weather API Error: {e}")
    return {"temp": None, "humidity": None, "weather_main": "Unknown", "rain_1h": 0}

def get_traffic_data(origin, destination):
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin}&destinations={destination}&departure_time=now&key={GOOGLE_MAPS_KEY}"
    try:
        response = requests.get(url, timeout=10).json()
        if response.get("status") == "OK":
            element = response["rows"][0]["elements"][0]
            if element.get("status") == "OK":
                distance_m = element["distance"]["value"]
                normal_duration_s = element["duration"]["value"]
                in_traffic_duration_s = element.get("duration_in_traffic", {}).get("value", normal_duration_s)
                
                # Calculate delay ratio
                delay_ratio = round(in_traffic_duration_s / normal_duration_s, 2) if normal_duration_s > 0 else 1.0
                
                return {
                    "distance_km": round(distance_m / 1000, 2),
                    "normal_duration_min": round(normal_duration_s / 60, 2),
                    "traffic_duration_min": round(in_traffic_duration_s / 60, 2),
                    "delay_ratio": delay_ratio
                }
    except Exception as e:
        print(f"Traffic API Error: {e}")
    return {"distance_km": None, "normal_duration_min": None, "traffic_duration_min": None, "delay_ratio": None}

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    weather = get_weather()
    
    file_exists = os.path.isfile(CSV_FILE)
    
    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        
        # Write CSV header if file is being created for the first time
        if not file_exists:
            writer.writerow([
                "timestamp", "corridor_id", "corridor_name", 
                "distance_km", "normal_duration_min", "traffic_duration_min", "delay_ratio",
                "temperature_c", "humidity_pct", "weather_condition", "rain_1h_mm"
            ])
            
        for c in CORRIDORS:
            traffic = get_traffic_data(c["origin"], c["destination"])
            writer.writerow([
                timestamp, c["id"], c["name"],
                traffic["distance_km"], traffic["normal_duration_min"], 
                traffic["traffic_duration_min"], traffic["delay_ratio"],
                weather["temp"], weather["humidity"], 
                weather["weather_main"], weather["rain_1h"]
            ])
            print(f"Logged data for: {c['name']}")

if __name__ == "__main__":
    main()
