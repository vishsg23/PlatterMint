from urllib.parse import quote

PRICE_RANGES = {
    0: "Under ₹200 for one",
    1: "₹200–400 for one",
    2: "₹400–800 for one",
    3: "₹800–1500 for one",
    4: "₹1500+ for one",
}


def price_display(price_level):
    """Turns Google's 0-4 price_level into a readable estimate instead of just ₹₹₹."""
    if price_level is None:
        return "Price not available"
    symbols = "₹" * (price_level + 1)
    range_text = PRICE_RANGES.get(price_level, "")
    return f"{symbols}  (approx. {range_text})" if range_text else symbols


def google_maps_search_url(name, location):
    """Free -- just opens Google Maps search for this restaurant. No API key needed."""
    query = quote(f"{name} {location}")
    return f"https://www.google.com/maps/search/?api=1&query={query}"


def google_maps_directions_url(name, location):
    """Free -- opens Google Maps with directions pre-filled. No API key needed."""
    destination = quote(f"{name} {location}")
    return f"https://www.google.com/maps/dir/?api=1&destination={destination}"
