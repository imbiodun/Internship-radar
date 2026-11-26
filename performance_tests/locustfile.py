from locust import HttpUser, between, task


class RadarUser(HttpUser):

    wait_time = between(1,3)


    @task
    def check_progress(self):
        with self.client.get(
            "/api/progress",
            catch_response=True
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"Unexpected status: {response.status_code}"
                )
                return

            try:
                data = response.json()
            except ValueError:
                response.failure("Invalid JSON response")
                return

            if not isinstance(data, dict):
                response.failure(
                    f"Expected a JSON object, got: {type(data).__name__}"
                )

            elif not isinstance(data.get("stage"), str):
                response.failure("Missing or invalid stage")

            elif not isinstance(data.get("detail"), str):
                response.failure("Missing or invalid detail")

            else:
                response.success()

    @task
    def get_saved_postings(self):
        with self.client.get(
            "/api/postings",
            catch_response= True
        ) as response:
            
            if response.status_code != 200:
                response.failure(
                    f"Unexpected status: {response.status_code}"
                )
                return

            try: 
                data = response.json()
            except ValueError:
                response.failure("Invalid JSON response")
                return

            
            if not isinstance(data, dict):
                response.failure(
                    f"Expected a JSON object, got: {type(data).__name__}"
                )
               

            elif not isinstance(data.get("postings"), list):
                response.failure("Missing or invalid postings list")
                

            else:
                response.success()


    @task
    def get_stats(self):
        with self.client.get(
            "/api/stats", 
            catch_response = True
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"Unexpected status: {response.status_code}"
                )
                return

            try:
                data = response.json()
            except ValueError:
                response.failure("Invalid JSON response")
                return

            if not isinstance(data, dict):
                response.failure(
                f"Expected a JSON object, got: {type(data).__name__}")
              

            elif not isinstance(data.get("counters"), dict):
                response.failure("Missing or invalid counters object")
              
            elif not isinstance(data.get("runs"), list):
                response.failure("Missing or invalid runs list")
                return

            elif data.get("cache_only") is not True:
                response.failure("Cache mode only is not enabled")
               
            
            else:
                response.success()