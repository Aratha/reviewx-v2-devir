"""Route classes shared by the settings endpoints whose write methods exist only locally."""

from starlette.routing import Match
from starlette.types import Scope

from app.api.validation import envelope_validation_route

_EnvelopeRoute = envelope_validation_route(422)


class MethodScopedRoute(_EnvelopeRoute):  # type: ignore[misc,valid-type]
    """A route that does not claim other methods on its path.

    Starlette answers 405 when a path exists with another method. The settings pages register
    their write methods only in the local environment; with this class a nonprod write request
    finds no route at all and receives 404, as sql-review 002 Requirement 5 and 006
    Requirement 13 require.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope = super().matches(scope)
        if match is Match.PARTIAL:
            return Match.NONE, {}
        return match, child_scope
