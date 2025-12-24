from typing import Optional
from google.adk.runners import InMemoryRunner
from google.genai import types


class AdkRunner:
    def __init__(self, agent, app_name: str = "cla_evidence_extractor", user_id: str = "user"):
        self.agent = agent
        self.runner = InMemoryRunner(agent=agent, app_name=app_name)
        self.user_id = user_id
        self.session_id: Optional[str] = None

    async def _ensure_session(self) -> str:
        if self.session_id:
            return self.session_id
        session = await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id=self.user_id,
        )
        self.session_id = session.id
        return self.session_id

    async def run_text(self, text: str) -> str:
        sid = await self._ensure_session()
        content = types.Content(role="user", parts=[types.Part.from_text(text=text)])

        last = ""
        # runner.run is sync generator; iterate normally
        for event in self.runner.run(user_id=self.user_id, session_id=sid, new_message=content):
            if getattr(event, "content", None) and event.content.parts:
                part0 = event.content.parts[0]
                if getattr(part0, "text", None):
                    last = part0.text
        return last
