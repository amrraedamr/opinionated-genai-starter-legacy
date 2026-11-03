import asyncio
import importlib
import pkgutil
from collections.abc import AsyncGenerator

import base.services.prompt.templates as pkg
from base.models.definitions.cache import CacheChannels
from base.models.view_models.prompt import Prompt
from base.services.cache.factory import get_cache_service
from base.services.common.meta import Singleton
from base.services.configuration import settings
from base.services.logging.console import ConsoleLoggerService
from base.services.store.prompt import PromptStore


class PromptLoader(metaclass=Singleton):
    """In-memory registry of the prompts the app can render.

    Templates arrive from code via `@register_prompt`. When the app opts into
    stored prompts, the templates held in the database win over the code ones,
    both at startup and on every reload published to the other workers.
    """

    def __init__(self) -> None:
        self._prompts: dict[str, Prompt] = {}
        self._templates_loaded: bool = False
        self._logger: ConsoleLoggerService = ConsoleLoggerService()
        self._watcher: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        """Import the prompt templates and follow the stored overrides.

        Call once at startup. With `LOAD_PROMPTS_FROM_DB` on, the stored
        templates are applied before the first request is served and
        re-applied for as long as the app runs.
        """
        self.load_templates()
        self._templates_loaded = True

        if settings.load_prompts_from_db:
            await self._areload()
            self._watcher = asyncio.create_task(
                self._awatch_reloads(), name="prompt-reload"
            )

        self._logger.info(
            "PromptLoader initialized with %d prompts", len(self._prompts)
        )

    async def shutdown(self) -> None:
        """Stop following reloads. Call once at shutdown."""
        if self._watcher is not None:
            self._watcher.cancel()
            await asyncio.gather(self._watcher, return_exceptions=True)
            self._watcher = None
        self._logger.info("PromptLoader shut down")

    async def apublish_reload(self) -> None:
        """Tell every worker, including this one, to re-read stored prompts.

        Whatever writes a new active version calls this; no worker has to be
        restarted for the change to take effect.
        """
        await get_cache_service().apublish(self._channel(), "reload")

    def load_templates(self) -> None:
        """Import all template modules so @register_prompt decorators fire.

        Must be called ONCE at app startup.
        """
        if self._templates_loaded:
            self._logger.warning("Templates already loaded, skipping")
            return

        for info in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg.__name__}."):
            importlib.import_module(info.name)

        self._logger.info("Loaded prompt templates: %d", len(self._prompts))

    def register(self, prompt: Prompt) -> None:
        """Register a prompt. Called by the @register_prompt decorator."""
        if prompt.key in self._prompts:
            self._logger.warning(
                "Prompt key %s already registered, overwriting", prompt.key
            )
        self._prompts[prompt.key] = prompt
        self._logger.info("Registered prompt: %s", prompt.key)

    def get(self, key: str) -> Prompt:
        prompt: Prompt | None = self._prompts.get(key)
        if prompt is None:
            raise KeyError(f"Prompt not found: {key}")
        return prompt

    def list_keys(self) -> list[str]:
        return list(self._prompts.keys())

    @staticmethod
    def _channel() -> str:
        return CacheChannels.PROMPT_RELOAD.for_app(settings.app_name)

    async def _areload(self) -> int:
        """Override the registered prompts with the stored templates.

        A stored row carries the template only, so name and description stay
        with the prompt declared in code. A key nobody registered is skipped
        rather than invented. Returns how many were overridden.
        """
        applied = 0
        for key, template in (await PromptStore().aget_active_templates()).items():
            current = self._prompts.get(key)
            if current is None:
                self._logger.warning(
                    "Stored prompt %s has no template registered in code; skipping",
                    key,
                )
                continue
            self._prompts[key] = Prompt(
                key=key,
                name=current.name,
                description=current.description,
                template=template,
            )
            applied += 1

        self._logger.info("Applied %d stored prompt override(s)", applied)
        return applied

    async def _awatch_reloads(self) -> None:
        """Re-apply the stored prompts whenever a reload is published.

        A failed reload must not end the subscription, or this worker would
        serve stale prompts for the rest of its life.
        """
        while True:
            try:
                events: AsyncGenerator[str, None] = get_cache_service().subscribe(
                    self._channel()
                )
                async for _ in events:
                    await self._areload()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Prompt reload subscription failed; retrying")
                await asyncio.sleep(1)
