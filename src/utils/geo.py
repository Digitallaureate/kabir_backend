# app/api/utils/geo.py
from math import radians, sin, cos, asin, sqrt

# Haversine formula to calculate the great-circle distance between two points
# on the Earth given their latitude and longitude in decimal degrees
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = rlon2 - rlon1
    dlat = rlat2 - rlat1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return 6371.0 * c  # km

# for formatting the distance nicely
def format_distance(distance_km: float) -> str:
    """
    Format distance with appropriate units
    - If >= 1 km: return "X.XX km"
    - If < 1 km: return "XXX m"
    """
    if distance_km >= 1.0:
        return f"{distance_km:.2f} km"
    else:
        # Convert to meters and round to nearest meter
        distance_m = distance_km * 1000
        return f"{int(round(distance_m))} m"
