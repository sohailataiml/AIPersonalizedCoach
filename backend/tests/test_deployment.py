"""Deployment-sensitive behaviour.

These protect the properties that only matter once the app leaves a laptop, and
that are easy to get wrong silently:

* **Neo4j mode means Neo4j.** No silent fall back to the in-memory backend.
  Swapping the storage engine underneath a safety system because a database was
  slow is the failure this suite exists to prevent.
* **Bootstrap is idempotent.** A redeploy merges; it never wipes and never
  duplicates.
* **Readiness tells the truth.** Liveness ignores the graph, readiness does not.
* **Nothing leaks.** No credential, URI or stack trace in any response.

The Neo4j-backed tests run against a live container when one is reachable and
skip otherwise, so the suite stays runnable with no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings
from app.graph.bootstrap import (
    SEED_VERSION,
    BootstrapReport,
    GraphBackendUnavailableError,
    connect_with_retry,
    ensure_seeded,
    safe_target,
    verify,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET = "sup3r-s3cret-neo4j-pw"


# --- configuration -----------------------------------------------------------


class TestConfiguration:
    def test_memory_is_the_default_so_local_runs_need_no_database(self):
        """Asserts the declared default, not the ambient environment.

        Instantiating Settings() would read GRAPH_BACKEND from the environment,
        so this test would pass or fail depending on how the suite was invoked
        - which is exactly the kind of environment-sensitivity a deployment
        suite should not have.
        """
        assert Settings.model_fields["graph_backend"].default == "memory"

    def test_render_style_config_selects_neo4j(self):
        settings = Settings(
            graph_backend="neo4j", neo4j_host="future-coach-neo4j", environment="render"
        )
        assert settings.graph_backend == "neo4j"
        assert settings.bolt_uri == "bolt://future-coach-neo4j:7687"

    def test_a_platform_supplied_host_wins_over_a_static_uri(self):
        """The hostname is resolved by Render, never guessed in a config file."""
        settings = Settings(
            neo4j_uri="bolt://localhost:7687", neo4j_host="future-coach-neo4j"
        )
        assert settings.bolt_uri == "bolt://future-coach-neo4j:7687"

    def test_without_a_host_the_local_uri_is_used(self):
        assert Settings().bolt_uri == "bolt://localhost:7687"

    def test_a_bare_frontend_host_becomes_an_https_origin(self):
        """Render's service reference yields a hostname, not an origin."""
        settings = Settings(frontend_origin="future-coach-frontend.onrender.com")
        assert "https://future-coach-frontend.onrender.com" in settings.allowed_origins

    def test_an_explicit_scheme_is_respected(self):
        settings = Settings(frontend_origin="http://staging.example.com/")
        assert "http://staging.example.com" in settings.allowed_origins

    def test_local_development_origins_survive_a_deployed_origin(self):
        settings = Settings(frontend_origin="future-coach-frontend.onrender.com")
        assert "http://localhost:3000" in settings.allowed_origins

    def test_cors_is_never_a_wildcard(self):
        """The API allows credentials; a wildcard with credentials is invalid."""
        assert "*" not in Settings().allowed_origins
        assert "*" not in Settings(frontend_origin="x.onrender.com").allowed_origins

    def test_mcp_dns_rebinding_protection_stays_enabled(self):
        """The allow-list is configured; the protection is never turned off."""
        settings = Settings(mcp_allowed_hosts=["future-coach-backend.onrender.com"])
        assert settings.mcp_allowed_hosts
        assert "*" not in settings.mcp_allowed_hosts


class TestSecretsAreNotLogged:
    def test_safe_target_keeps_only_scheme_host_and_port(self):
        rendered = safe_target(f"bolt://neo4j:{SECRET}@private-host:7687")
        assert SECRET not in rendered
        assert rendered == "bolt://private-host:7687"

    def test_an_unreachable_backend_reports_without_the_password(self):
        settings = Settings(
            graph_backend="neo4j",
            neo4j_host="203.0.113.1",  # TEST-NET-3, guaranteed unroutable
            neo4j_password=SECRET,
            neo4j_connect_attempts=1,
            neo4j_connect_backoff_seconds=0,
            neo4j_connect_timeout_seconds=0.25,
        )
        from app.ontology.loader import get_ontology

        with pytest.raises(GraphBackendUnavailableError) as caught:
            connect_with_retry(settings, get_ontology(), sleep=lambda _: None)

        assert SECRET not in str(caught.value)
        assert "203.0.113.1" in str(caught.value)


class TestConnectRetry:
    def test_attempts_are_bounded_and_backoff_grows(self):
        """No infinite retry: a misconfiguration must surface, not hang."""
        settings = Settings(
            graph_backend="neo4j",
            neo4j_host="203.0.113.1",
            neo4j_connect_attempts=3,
            neo4j_connect_backoff_seconds=1,
            neo4j_connect_max_backoff_seconds=4,
            neo4j_connect_timeout_seconds=0.25,
        )
        from app.ontology.loader import get_ontology

        slept: list[float] = []
        with pytest.raises(GraphBackendUnavailableError):
            connect_with_retry(settings, get_ontology(), sleep=slept.append)

        assert len(slept) == 2  # attempts - 1
        assert slept == [1, 2]

    def test_a_single_attempt_is_honoured(self):
        settings = Settings(
            graph_backend="neo4j",
            neo4j_host="203.0.113.1",
            neo4j_connect_attempts=1,
            neo4j_connect_backoff_seconds=0,
            neo4j_connect_timeout_seconds=0.25,
        )
        from app.ontology.loader import get_ontology

        slept: list[float] = []
        with pytest.raises(GraphBackendUnavailableError):
            connect_with_retry(settings, get_ontology(), sleep=slept.append)
        assert slept == []


class TestNoSilentFallback:
    def test_neo4j_mode_never_degrades_to_memory(self, monkeypatch):
        """The regression this suite exists for."""
        from app.api import deps
        from app.ontology.loader import get_ontology

        settings = Settings(
            graph_backend="neo4j",
            neo4j_host="203.0.113.1",
            neo4j_connect_attempts=1,
            neo4j_connect_backoff_seconds=0,
            neo4j_connect_timeout_seconds=0.25,
        )
        with pytest.raises(GraphBackendUnavailableError):
            deps._build_repository(settings, get_ontology())

    def test_memory_mode_still_builds_without_a_database(self):
        from app.api import deps
        from app.ontology.loader import get_ontology

        repository, backend, report = deps._build_repository(
            Settings(graph_backend="memory"), get_ontology()
        )
        assert backend == "memory"
        assert report.seeded is True
        assert repository.list_exercises()


# --- verification ------------------------------------------------------------


class TestSeedVerification:
    def test_a_correct_graph_reports_no_problems(self, repository):
        assert verify(repository.stats(), Settings().exercises_path) == []

    def test_a_short_graph_is_rejected(self):
        assert verify({"node:Exercise": 3}, Settings().exercises_path)

    def test_missing_edges_are_reported(self, repository):
        stats = dict(repository.stats())
        stats["edge:CONTRAINDICATES"] = 0
        problems = verify(stats, Settings().exercises_path)
        assert any("CONTRAINDICATES" in problem for problem in problems)


# --- health ------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    import app.mcp.server as mcp_server_module
    from app.main import create_app

    monkeypatch.setattr(mcp_server_module, "_asgi_app", None)
    with TestClient(create_app()) as client:
        yield client


class TestHealthEndpoints:
    def test_liveness_does_not_depend_on_the_graph(self, client):
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_readiness_reports_the_backend_and_seed_state(self, client):
        response = client.get("/health/ready")
        assert response.status_code == 200
        body = response.json()

        assert body["status"] == "ready"
        assert body["graph_reachable"] is True
        assert body["graph_seeded"] is True
        assert body["seed_version"] == SEED_VERSION
        assert body["problems"] == []

    def test_readiness_is_503_when_the_graph_is_unavailable(self, client):
        """A failing graph must not be reported as a healthy deploy."""
        from app.api import deps

        services = deps.get_services()
        original = services.bootstrap
        services.bootstrap = BootstrapReport(
            backend="neo4j", reachable=False, seeded=False, problems=["unreachable"]
        )
        try:
            response = client.get("/health/ready")
            assert response.status_code == 503
            assert response.json()["status"] == "not_ready"
            assert response.json()["graph_reachable"] is False
        finally:
            services.bootstrap = original

    def test_health_reports_deployment_facts_without_connection_detail(self, client):
        body = client.get("/api/health").json()
        assert body["environment"] == "local"
        assert body["graph_seeded"] is True
        assert body["ontology_mappings"] == 29

    def test_no_health_response_leaks_a_credential(self, client):
        for path in ("/health/live", "/health/ready", "/api/health"):
            payload = client.get(path).text.lower()
            for secret in ("password", "bolt://", "neo4j://", "traceback", "@"):
                assert secret not in payload, path


# --- Blueprint ---------------------------------------------------------------


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return yaml.safe_load((REPO_ROOT / "render.yaml").read_text(encoding="utf-8"))


class TestRenderBlueprint:
    def _service(self, blueprint: dict, name: str) -> dict:
        return next(s for s in blueprint["services"] if s["name"] == name)

    def test_three_services_are_defined(self, blueprint):
        names = {service["name"] for service in blueprint["services"]}
        assert names == {
            "future-coach-neo4j",
            "future-coach-backend",
            "future-coach-frontend",
        }

    def test_neo4j_is_private_with_a_pinned_image(self, blueprint):
        neo4j = self._service(blueprint, "future-coach-neo4j")
        assert neo4j["type"] == "pserv"  # no public URL is ever assigned
        assert neo4j["runtime"] == "image"
        assert neo4j["image"]["url"].endswith(":5.26-community")
        assert "latest" not in neo4j["image"]["url"]

    def test_neo4j_has_a_persistent_disk_at_data(self, blueprint):
        disk = self._service(blueprint, "future-coach-neo4j")["disk"]
        assert disk["mountPath"] == "/data"
        assert disk["sizeGB"] >= 1

    def test_the_disk_service_is_on_a_paid_plan(self, blueprint):
        """Render disks and private-network ingress both require paid plans."""
        assert self._service(blueprint, "future-coach-neo4j")["plan"] != "free"

    def test_all_services_share_a_region(self, blueprint):
        """Render's private network is regional."""
        regions = {service["region"] for service in blueprint["services"]}
        assert len(regions) == 1

    def test_nothing_free_is_addressed_over_the_private_network(self, blueprint):
        """A free service can SEND private traffic but cannot RECEIVE it.

        So any service named as the target of a `fromService` host/port/hostport
        reference has to be on a paid plan, or the reference resolves to an
        address that refuses the connection. Asserted rather than remembered:
        an earlier draft of this Blueprint pointed the frontend at a `free`
        backend over `hostport`, which would have failed only once deployed.
        """
        private_properties = {"host", "port", "hostport"}
        referenced = {
            entry["fromService"]["name"]
            for service in blueprint["services"]
            for entry in service.get("envVars", [])
            if entry.get("fromService", {}).get("property") in private_properties
        }
        assert referenced, "expected at least one private-network reference"
        for name in referenced:
            assert self._service(blueprint, name)["plan"] != "free", (
                f"{name} is addressed privately but cannot receive that traffic"
            )

    def test_public_origins_are_not_private_service_references(self, blueprint):
        """CORS origins and the proxy target must be public URLs.

        `fromService` exposes only private addresses, so referencing one here
        would put an internal hostname in Access-Control-Allow-Origin (matching
        nothing) or proxy over plain-HTTP private DNS.
        """
        backend = self._env(self._service(blueprint, "future-coach-backend"))
        frontend = self._env(self._service(blueprint, "future-coach-frontend"))
        for env, key in ((backend, "FRONTEND_ORIGIN"), (frontend, "BACKEND_ORIGIN")):
            assert "fromService" not in env[key]
            assert env[key]["value"].startswith("https://")

    def test_the_backend_runs_against_neo4j(self, blueprint):
        env = self._env(self._service(blueprint, "future-coach-backend"))
        assert env["GRAPH_BACKEND"]["value"] == "neo4j"
        assert env["ENVIRONMENT"]["value"] == "render"

    def test_the_neo4j_host_comes_from_a_service_reference(self, blueprint):
        env = self._env(self._service(blueprint, "future-coach-backend"))
        reference = env["NEO4J_HOST"]["fromService"]
        assert reference["name"] == "future-coach-neo4j"
        assert reference["type"] == "pserv"
        assert reference["property"] == "host"

    def test_secrets_are_never_committed(self, blueprint):
        for service in blueprint["services"]:
            for entry in service.get("envVars", []):
                if entry["key"] in {"NEO4J_AUTH", "NEO4J_PASSWORD"}:
                    assert entry.get("sync") is False
                    assert "value" not in entry

    def test_no_literal_password_appears_anywhere_in_the_blueprint(self):
        text = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8").lower()
        assert "futurecoach" not in text

    def test_the_backend_health_check_uses_readiness(self, blueprint):
        backend = self._service(blueprint, "future-coach-backend")
        assert backend["healthCheckPath"] == "/health/ready"

    def test_the_frontend_receives_no_graph_configuration(self, blueprint):
        env = self._env(self._service(blueprint, "future-coach-frontend"))
        for key in env:
            assert "NEO4J" not in key.upper()

    def test_the_frontend_never_receives_a_secret(self, blueprint):
        env = self._env(self._service(blueprint, "future-coach-frontend"))
        assert all(entry.get("sync") is not False for entry in env.values())

    def test_mcp_host_protection_is_configured_not_disabled(self, blueprint):
        env = self._env(self._service(blueprint, "future-coach-backend"))
        hosts = json.loads(env["MCP_ALLOWED_HOSTS"]["value"])
        assert hosts and "*" not in hosts

    @staticmethod
    def _env(service: dict) -> dict:
        return {entry["key"]: entry for entry in service.get("envVars", [])}


class TestFrontendBundleHasNoSecrets:
    def test_no_neo4j_configuration_reaches_client_code(self):
        """A grep-level guard over everything shipped to the browser."""
        roots = [REPO_ROOT / "frontend" / d for d in ("app", "components", "lib")]
        for root in roots:
            for path in root.rglob("*.ts*"):
                text = path.read_text(encoding="utf-8").lower()
                for forbidden in ("neo4j_password", "bolt://", "neo4j://"):
                    assert forbidden not in text, f"{path}: {forbidden}"


# --- Neo4j-backed bootstrap --------------------------------------------------


def _neo4j_repository():
    try:
        from app.core.config import get_settings
        from app.graph.neo4j_repository import Neo4jGraphRepository
        from app.ontology.loader import get_ontology

        settings = get_settings()
        return Neo4jGraphRepository.connect(
            settings.bolt_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            settings.neo4j_database,
            settings.exercises_path,
            settings.member_context_path,
            get_ontology(),
        )
    except Exception:  # noqa: BLE001 - absence of a database is not a failure
        return None


@pytest.fixture(scope="module")
def neo4j_repository():
    repository = _neo4j_repository()
    if repository is None:
        pytest.skip("Neo4j is not reachable; bootstrap tests skipped")
    try:
        yield repository
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()


class TestIdempotentBootstrap:
    """A redeploy must merge, never wipe and never duplicate."""

    def test_bootstrap_seeds_and_verifies(self, neo4j_repository):
        report = ensure_seeded(neo4j_repository, Settings())
        assert report.reachable is True
        assert report.seeded is True
        assert report.problems == []

    def test_running_it_again_changes_nothing(self, neo4j_repository):
        settings = Settings()
        first = ensure_seeded(neo4j_repository, settings)
        second = ensure_seeded(neo4j_repository, settings)

        assert first.stats == second.stats
        # The version marker means a warm database is not re-merged at all.
        assert second.wrote is False

    def test_no_duplicate_nodes_or_relationships_after_repeat_seeding(
        self, neo4j_repository
    ):
        settings = Settings()
        before = neo4j_repository.stats()
        neo4j_repository.seed(wipe=False)  # force the merge path
        after = neo4j_repository.stats()

        assert before == after
        assert verify(after, settings.exercises_path) == []

    def test_ontology_mappings_survive_reseeding(self, neo4j_repository):
        stats = neo4j_repository.stats()
        assert stats.get("node:OntologyConcept") == 29
        assert stats.get("edge:SKOS_EXACT_MATCH", 0) > 0

    def test_member_relationships_survive_reseeding(self, neo4j_repository):
        stats = neo4j_repository.stats()
        assert stats.get("edge:HAS_INJURY", 0) > 0
        assert stats.get("edge:HAS_EQUIPMENT", 0) > 0

    def test_the_seed_marker_is_recorded_and_hidden_from_the_explorer(
        self, neo4j_repository
    ):
        from app.domain.graph_explorer import EXPLORABLE_KINDS

        assert neo4j_repository.read_seed_version() == SEED_VERSION
        assert "SeedMetadata" not in EXPLORABLE_KINDS
        assert neo4j_repository.search_nodes("seed", limit=50).hits == []
