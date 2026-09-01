import os
import csv
import time
from datetime import datetime, timezone, timedelta
import requests

# Retrieve API keys from GitHub Secrets
GOOGLE_MAPS_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
OPENWEATHER_KEY = os.environ.get('OPENWEATHER_API_KEY')

# Standardized Srinagar Corridors with Locked Highway Midpoints
CORRIDORS = [
    {
        "id": 1,
        "name": "Lal Chowk to Hyderpora",
        "origin_lat": 34.0728, "origin_lng": 74.8097,   # Lal Chowk (Ghanta Ghar)
        "via_lat": 34.0538, "via_lng": 74.8005,         # Rambagh Flyover Midpoint
        "dest_lat": 34.0360, "dest_lng": 74.7876        # Hyderpora Bypass Junction
    },
    {
        "id": 2,
        "name": "Dalgate to Pantha Chowk",
        "origin_lat": 34.0740, "origin_lng": 74.8285,   # Dalgate Bridge
        "via_lat": 34.0552, "via_lng": 74.8432,         # BB Cantt / Shivpora Midpoint
        "dest_lat": 34.0298, "dest_lng": 74.8645        # Pantha Chowk Expressway Junction
    },
    {
        "id": 3,
        "name": "Jahangir Chowk to Parimpora",
        "origin_lat": 34.0718, "origin_lng": 74.8023,   # Jahangir Chowk Flyover
        "via_lat": 34.0815, "via_lng": 74.7780,         # Qamarwari Chowk Midpoint
        "dest_lat": 34.0882, "dest_lng": 74.7554        # Parimpora Bypass Junction
    }
]

RAW_DIST_CSV = "raw_distance_api.csv"
ENRICHED_DIST_CSV = "enriched_distance_api.csv"
RAW_ROUTES_CSV = "raw_routes_api.csv"
ENRICHED_ROUTES_CSV = "enriched_routes_api.csv"

def fetch_with_retry(url, method="GET", json_payload=None, headers=None, max_attempts=3, timeout=15):
    for attempt in range(1, max_attempts + 1):
        try:
            if method == "POST":
                res = requests.post(url, json=json_payload, headers=headers, timeout=timeout)
            else:
                res = requests.get(url, headers=headers, timeout=timeout)
            
            if res.status_code != 200:
                print(f"API Error ({res.status_code}) attempt {attempt}: {res.text}")
                if attempt == max_attempts:
                    return None, f"HTTP_{res.status_code}"
                time.sleep(2)
                continue
                
            return res.json(), "OK"
        except requests.exceptions.RequestException as e:
            if attempt == max_attempts:
                return None, f"HTTP_ERROR_{type(e).__name__}"
            time.sleep(2)

def get_weather():
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Srinagar,IN&appid={OPENWEATHER_KEY}&units=metric"
    data, status = fetch_with_retry(url)
    if data and data.get("cod") == 200:
        return {
            "weather_api_status": "OK",
            "temp": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "weather_main": data["weather"][0]["main"],
            "rain_1h": data.get("rain", {}).get("1h", 0)
        }
    return {"weather_api_status": status, "temp": None, "humidity": None, "weather_main": None, "rain_1h": None}

def get_distance_matrix_data(o_lat, o_lng, d_lat, d_lng):
    origin_str = f"{o_lat},{o_lng}"
    dest_str = f"{d_lat},{d_lng}"
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_str}&destinations={dest_str}&departure_time=now&key={GOOGLE_MAPS_KEY}"
    data, http_status = fetch_with_retry(url)
    
    if not data or data.get("status") != "OK":
        return {"route_status": http_status, "traffic_data_status": "UNAVAILABLE", "distance_km": None, "reference_duration_min": None, "actual_duration_min": None, "reference_speed_kmh": None, "actual_speed_kmh": None, "delay_ratio": None}

    element = data["rows"][0]["elements"][0]
    if element.get("status") == "OK":
        distance_m = element["distance"]["value"]
        ref_duration_s = element["duration"]["value"]
        act_duration_s = element.get("duration_in_traffic", {}).get("value")
        
        distance_km = round(distance_m / 1000, 2)
        ref_duration_min = round(ref_duration_s / 60, 2)
        act_duration_min = round(act_duration_s / 60, 2) if act_duration_s else None
        
        delay_ratio = round(act_duration_min / ref_duration_min, 3) if act_duration_min and ref_duration_min > 0 else 1.0
        ref_speed_kmh = round(distance_km / (ref_duration_min / 60), 2) if ref_duration_min > 0 else 0.0
        act_speed_kmh = round(distance_km / (act_duration_min / 60), 2) if act_duration_min and act_duration_min > 0 else 0.0

        return {
            "route_status": "OK", "traffic_data_status": "AVAILABLE" if act_duration_s else "UNAVAILABLE",
            "distance_km": distance_km, "reference_duration_min": ref_duration_min,
            "actual_duration_min": act_duration_min, "reference_speed_kmh": ref_speed_kmh,
            "actual_speed_kmh": act_speed_kmh, "delay_ratio": delay_ratio
        }
    return {"route_status": element.get("status"), "traffic_data_status": "UNAVAILABLE", "distance_km": None, "reference_duration_min": None, "actual_duration_min": None, "reference_speed_kmh": None, "actual_speed_kmh": None, "delay_ratio": None}

def get_routes_api_data(o_lat, o_lng, via_lat, via_lng, d_lat, d_lng):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters"
    }
    payload = {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lng}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lng}}},
        "intermediates": [{"location": {"latLng": {"latitude": via_lat, "longitude": via_lng}}, "via": True}],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL"
    }
    
    data, http_status = fetch_with_retry(url, method="POST", json_payload=payload, headers=headers)
    if not data or "routes" not in data or len(data["routes"]) == 0:
        return {"route_status": http_status, "traffic_data_status": "UNAVAILABLE", "distance_km": None, "reference_duration_min": None, "actual_duration_min": None, "reference_speed_kmh": None, "actual_speed_kmh": None, "delay_ratio": None}

    try:
        route = data["routes"][0]
        distance_m = route.get("distanceMeters", 0)
        ref_duration_s = float(route.get("staticDuration", "0s").replace("s", ""))
        act_duration_s = float(route.get("duration", "0s").replace("s", ""))
        
        distance_km = round(distance_m / 1000, 2)
        ref_duration_min = round(ref_duration_s / 60, 2)
        act_duration_min = round(act_duration_s / 60, 2)
        
        delay_ratio = round(act_duration_min / ref_duration_min, 3) if ref_duration_min > 0 else 1.0
        ref_speed_kmh = round(distance_km / (ref_duration_min / 60), 2) if ref_duration_min > 0 else 0.0
        act_speed_kmh = round(distance_km / (act_duration_min / 60), 2) if act_duration_min > 0 else 0.0

        return {
            "route_status": "OK", "traffic_data_status": "AVAILABLE",
            "distance_km": distance_km, "reference_duration_min": ref_duration_min,
            "actual_duration_min": act_duration_min, "reference_speed_kmh": ref_speed_kmh,
            "actual_speed_kmh": act_speed_kmh, "delay_ratio": delay_ratio
        }
    except Exception as e:
        return {"route_status": f"EXCEPTION_{type(e).__name__}", "traffic_data_status": "UNAVAILABLE", "distance_km": None, "reference_duration_min": None, "actual_duration_min": None, "reference_speed_kmh": None, "actual_speed_kmh": None, "delay_ratio": None}

def get_existing_slots(csv_file):
    existing = set()
    if os.path.isfile(csv_file):
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts, c_id = row.get("timestamp_ist", ""), row.get("corridor_id", "")
                if ts and c_id:
                    existing.add((str(c_id), ts[:13]))
    return existing

def check_peak_hour_srinagar(dt):
    time_decimal = dt.hour + (dt.minute / 60.0)
    return 1 if (8.5 <= time_decimal <= 10.5) or (17.0 <= time_decimal <= 19.5) else 0

def write_data(raw_csv, enriched_csv, raw_rows, enriched_rows):
    headers_raw = [
        "timestamp_ist", "corridor_id", "corridor_name", 
        "route_status", "traffic_data_status", "weather_api_status", 
        "distance_km", "reference_duration_min", "actual_duration_min", 
        "reference_speed_kmh", "actual_speed_kmh", "delay_ratio", 
        "congestion_index", "temperature_c", "humidity_pct", 
        "weather_condition", "rain_1h_mm"
    ]
    headers_enriched = [
        "timestamp_ist", "hour_of_day", "day_of_week", "is_peak_hour", 
        "corridor_id", "corridor_name", "route_status", "traffic_data_status", 
        "weather_api_status", "distance_km", "reference_duration_min", 
        "actual_duration_min", "reference_speed_kmh", "actual_speed_kmh", 
        "delay_ratio", "congestion_index", "temperature_c", "humidity_pct", 
        "weather_condition", "rain_1h_mm"
    ]

    if raw_rows:
        raw_exists = os.path.isfile(raw_csv)
        with open(raw_csv, mode="a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not raw_exists: w.writerow(headers_raw)
            w.writerows(raw_rows)
            
    if enriched_rows:
        enriched_exists = os.path.isfile(enriched_csv)
        with open(enriched_csv, mode="a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not enriched_exists: w.writerow(headers_enriched)
            w.writerows(enriched_rows)

def main():
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_tz)
    timestamp_ist = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    current_hour_slot = timestamp_ist[:13]
    
    hour_of_day, day_of_week, is_peak_hour = now_ist.hour, now_ist.strftime("%A"), check_peak_hour_srinagar(now_ist)
    existing_dist_slots, existing_routes_slots = get_existing_slots(RAW_DIST_CSV), get_existing_slots(RAW_ROUTES_CSV)
    weather = get_weather()
    
    dist_raw, dist_enriched, routes_raw, routes_enriched = [], [], []
    
    for c in CORRIDORS:
        c_id = str(c["id"])
        
        # 1. Distance Matrix API
        if (c_id, current_hour_slot) not in existing_dist_slots:
            td = get_distance_matrix_data(c["origin_lat"], c["origin_lng"], c["dest_lat"], c["dest_lng"])
            ci = round(td["delay_ratio"] - 1.0, 3) if td["delay_ratio"] is not None else None
            
            raw_r = [timestamp_ist, c["id"], c["name"], td["route_status"], td["traffic_data_status"], weather["weather_api_status"], td["distance_km"], td["reference_duration_min"], td["actual_duration_min"], td["reference_speed_kmh"], td["actual_speed_kmh"], td["delay_ratio"], ci, weather["temp"], weather["humidity"], weather["weather_main"], weather["rain_1h"]]
            enr_r = [timestamp_ist, hour_of_day, day_of_week, is_peak_hour] + raw_r[4:]
            dist_raw.append(raw_r); dist_enriched.append(enr_r)

        # 2. Routes API v2 (with Waypoint Forcing)
        if (c_id, current_hour_slot) not in existing_routes_slots:
            tr = get_routes_api_data(c["origin_lat"], c["origin_lng"], c["via_lat"], c["via_lng"], c["dest_lat"], c["dest_lng"])
            ci = round(tr["delay_ratio"] - 1.0, 3) if tr["delay_ratio"] is not None else None
            
            raw_r = [timestamp_ist, c["id"], c["name"], tr["route_status"], tr["traffic_data_status"], weather["weather_api_status"], tr["distance_km"], tr["reference_duration_min"], tr["actual_duration_min"], tr["reference_speed_kmh"], tr["actual_speed_kmh"], tr["delay_ratio"], ci, weather["temp"], weather["humidity"], weather["weather_main"], weather["rain_1h"]]
            enr_r = [timestamp_ist, hour_of_day, day_of_week, is_peak_hour] + raw_r[4:]
            routes_raw.append(raw_r); routes_enriched.append(enr_r)
            
    write_data(RAW_DIST_CSV, ENRICHED_DIST_CSV, dist_raw, dist_enriched)
    write_data(RAW_ROUTES_CSV, ENRICHED_ROUTES_CSV, routes_raw, routes_enriched)
    print(f"Logged route-locked dual API data for slot: {current_hour_slot}")

if __name__ == "__main__":
    main()
