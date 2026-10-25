"""Explicit reference points and deterministic great-circle distance filtering.

Reference points are convenient approximate downtown anchors, not official
neighborhood boundaries. Demo hotel coordinates are illustrative fixtures.
No travel times, geocoding, or transportation prices are inferred.
"""
from __future__ import annotations

from math import asin, cos, isfinite, radians, sin, sqrt

# name, latitude, longitude; approximate, user-visible and overridable.
DOWNTOWN_REFERENCES = {
    'boston': ('Boston City Hall area', 42.3603, -71.0581),
    'chicago': ('Chicago Loop reference', 41.8830, -87.6320),
    'new york': ('Lower Manhattan reference', 40.7128, -74.0060),
}


def downtown_reference(city):
    return DOWNTOWN_REFERENCES.get(city.strip().casefold())


def reference_for_segment(segment):
    if segment.location_preference == 'custom':
        return (segment.reference_name or 'Custom reference', segment.reference_latitude, segment.reference_longitude)
    return downtown_reference(segment.city)


def distance_km(lat1, lon1, lat2, lon2):
    """Haversine distance in kilometers; never round before filtering."""
    a1, a2 = radians(lat1), radians(lat2)
    delta_lat, delta_lon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(delta_lat / 2) ** 2 + cos(a1) * cos(a2) * sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(max(0.0, min(1.0, a))))


def offer_distance(offer, segment):
    reference = reference_for_segment(segment)
    if reference is None or offer.latitude is None or offer.longitude is None:
        return None
    return distance_km(offer.latitude, offer.longitude, reference[1], reference[2])


def filter_location(offers, segment):
    """Hard radius constraint: missing coordinates do not pass an active filter."""
    if segment.location_preference == 'any':
        return offers, []
    if reference_for_segment(segment) is None:
        return [], [f'No downtown reference for {segment.city}; choose a custom reference or any location.']
    accepted, missing, outside = [], 0, 0
    for offer in offers:
        distance = offer_distance(offer, segment)
        if distance is None:
            missing += 1
        elif distance <= segment.max_distance_km:
            accepted.append(offer)
        else:
            outside += 1
    warnings = []
    if outside:
        warnings.append(f'Location filter excluded {outside} offers outside the {segment.max_distance_km:g} km radius.')
    if missing:
        warnings.append(f'Location filter excluded {missing} offers with missing coordinates.')
    return accepted, warnings


def provider_coordinates(latitude, longitude):
    """Unavailable or invalid provider coordinates remain unknown, never (0, 0)."""
    try:
        lat, lon = float(latitude), float(longitude)
        if isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except (ValueError, TypeError):
        pass
    return None, None
