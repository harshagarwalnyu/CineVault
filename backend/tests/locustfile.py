from locust import HttpUser, task, between


class MovieUser(HttpUser):
    wait_time = between(1, 5)

    @task(3)
    def search_movies(self):
        self.client.get("/movies/search?q=action")

    @task(2)
    def get_trending(self):
        self.client.get("/trending")

    @task(1)
    def view_movie(self):
        # Assuming ID 1 exists
        self.client.get("/movies/1")

    @task(1)
    def get_recommendations(self):
        self.client.get("/recommendations/1")
