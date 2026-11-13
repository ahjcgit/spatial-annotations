"""Session-isolated retrieval via the existing API. VLM results never authorize reads."""

import httpx


class AnnotationClient:
    def __init__(self, base_url, pipeline, transport=None):
        self.base_url = base_url
        self.pipeline = pipeline
        self.transport = transport
        self._token = None
        self.epoch = 0

    def set_token(self, token):
        self.epoch += 1
        self._token = token
        self.pipeline.reset()  # Invalidate pending reasoning and retrieval; no note cache.

    async def retrieve(self, observation):
        pipeline = self.pipeline
        oid = observation.get("object_id")
        tid = observation["track_id"]
        generation = observation["generation"]
        epoch = self.epoch
        identity_epoch = pipeline.epoch
        token = self._token
        current = lambda: (
            epoch == self.epoch
            and token == self._token
            and pipeline.valid_identity(tid, generation, oid, identity_epoch)
        )
        if (
            not token
            or not oid
            or observation["identity_state"] != "matched"
            or not current()
        ):
            return []
        async with httpx.AsyncClient(
            base_url=self.base_url,
            transport=self.transport,
            timeout=10,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            headers = {"Authorization": "Bearer " + token}
            try:
                me = await client.get("/users/me", headers=headers)
                me.raise_for_status()
                result = []
                offset = 0
                while current():
                    r = await client.get(
                        f"/objects/{oid}/annotations",
                        params={"limit": 100, "offset": offset},
                        headers=headers,
                    )
                    r.raise_for_status()
                    page = r.json()
                    if not current():
                        return []
                    if not isinstance(page, list) or any(
                        a.get("object_id") != oid for a in page
                    ):
                        raise ValueError("Invalid annotation response")
                    result.extend(page)
                    if len(page) < 100:
                        return result if current() else []
                    offset += 100
                return []
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403) and epoch == self.epoch:
                    self.set_token(None)
                raise  # Caller logs only the exception category; never the response body.
