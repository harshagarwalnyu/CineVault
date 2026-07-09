import hashlib
from typing import Any, Optional


class AvailabilityAgent:
    """
    Agentic Mediator: Responsible for finding exactly WHERE to watch a movie.
    In 2026, this agent acts on behalf of the user to bypass siloed streaming discovery.

    (Note: For the prototype, this simulates a robust aggregator API like JustWatch or
    a swarm of custom playwright scrapers).
    """

    PLATFORMS = [
        {
            "id": "netflix",
            "name": "Netflix",
            "color": "#E50914",
            "icon": "netflix_icon.png",
        },
        {
            "id": "prime",
            "name": "Amazon Prime Video",
            "color": "#00A8E1",
            "icon": "prime_icon.png",
        },
        {"id": "max", "name": "Max", "color": "#002BE7", "icon": "max_icon.png"},
        {
            "id": "disney",
            "name": "Disney+",
            "color": "#113CCF",
            "icon": "disney_icon.png",
        },
        {"id": "hulu", "name": "Hulu", "color": "#1CE783", "icon": "hulu_icon.png"},
        {
            "id": "apple",
            "name": "Apple TV+",
            "color": "#000000",
            "icon": "apple_icon.png",
        },
    ]

    def __init__(self, user_subscriptions: Optional[list[str]] = None):
        # Default subscriptions for the prototype user
        self.user_subscriptions = user_subscriptions or ["netflix", "prime", "max"]

    def _deterministic_random_choice(self, movie_title: str) -> dict:
        """
        Uses a hash of the movie title to consistently return the same 'random' platform
        for the same movie, ensuring the UI doesn't flicker on re-renders.
        """
        hash_val = int(hashlib.md5(movie_title.encode("utf-8")).hexdigest(), 16)
        return self.PLATFORMS[hash_val % len(self.PLATFORMS)]

    def _deterministic_random_price(self, movie_title: str) -> float:
        hash_val = int(
            hashlib.md5((movie_title + "_price").encode("utf-8")).hexdigest(), 16
        )
        return [3.99, 4.99, 5.99, 14.99, 19.99][hash_val % 5]

    async def get_availability(self, movie_title: str) -> dict:
        """
        Returns streaming availability.
        Checks if the movie is in the user's current subscriptions.
        If not, provides a rental/purchase option.
        """

        # 1. The Agent searches the ecosystem (simulated)
        platform = self._deterministic_random_choice(movie_title)

        # 2. Negotiate with user's subscriptions
        is_subscribed = platform["id"] in self.user_subscriptions

        availability_data: dict[str, Any] = {
            "status": "available",
            "primary_action": None,  # The "Zero-Click" deep link action
            "secondary_actions": [],
        }

        deep_link = f"https://{platform['id']}.com/watch/{movie_title.lower().replace(' ', '-')}"

        if is_subscribed:
            availability_data["primary_action"] = {
                "type": "stream",
                "platform": platform,
                "deep_link": deep_link,
                "cost": 0.0,
                "label": f"Play on {platform['name']}",
            }
        else:
            # Suggest renting on Apple or Prime if not in subscription
            rental_platform = (
                self.PLATFORMS[1] if platform["id"] != "prime" else self.PLATFORMS[5]
            )
            price = self._deterministic_random_price(movie_title)

            availability_data["primary_action"] = {
                "type": "rent",
                "platform": rental_platform,
                "deep_link": f"https://{rental_platform['id']}.com/rent/{movie_title.lower().replace(' ', '-')}",
                "cost": price,
                "label": f"Rent on {rental_platform['name']} for ${price}",
            }

            availability_data["secondary_actions"].append(
                {
                    "type": "subscribe",
                    "platform": platform,
                    "deep_link": f"https://{platform['id']}.com/signup",
                    "cost": 15.99,
                    "label": f"Subscribe to {platform['name']}",
                }
            )

        return availability_data

    async def filter_accessible_only(self, recommendations: list[dict]) -> list[dict]:
        """
        Agentic Filter: Only return movies the user can actually click and watch *right now* for free.
        """
        accessible = []
        for rec in recommendations:
            avail = await self.get_availability(rec["title"])
            if avail["primary_action"] and avail["primary_action"]["type"] == "stream":
                rec["availability"] = avail
                accessible.append(rec)

        return accessible
