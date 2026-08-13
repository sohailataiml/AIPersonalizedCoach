"""Cypher used by the Neo4j backend.

Kept in one file so the graph logic is reviewable as *queries* rather than being
buried in Python. The two traversals that matter most are
``ANATOMICAL_CLOSURE`` and ``INJURY_AFFECTED_REGIONS`` - they are the Cypher
statement of the safety rule this whole system exists to enforce.
"""

from __future__ import annotations

# --- schema ------------------------------------------------------------------

CONSTRAINTS = [
    "CREATE CONSTRAINT exercise_id IF NOT EXISTS "
    "FOR (e:Exercise) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT region_id IF NOT EXISTS "
    "FOR (a:AnatomicalRegion) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT equipment_id IF NOT EXISTS "
    "FOR (q:Equipment) REQUIRE q.id IS UNIQUE",
    "CREATE CONSTRAINT muscle_id IF NOT EXISTS FOR (m:Muscle) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT pattern_id IF NOT EXISTS "
    "FOR (p:MovementPattern) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT member_id IF NOT EXISTS FOR (m:Member) REQUIRE m.id IS UNIQUE",
]

WIPE = "MATCH (n) DETACH DELETE n"

# --- ingest ------------------------------------------------------------------
# Nodes and edges are written generically from the KnowledgeGraph projection, so
# the in-memory and Neo4j graphs cannot drift apart.

MERGE_NODE = """
UNWIND $rows AS row
CALL apoc.merge.node([row.label], {key: row.key}, row.properties, {}) YIELD node
RETURN count(node) AS created
"""

MERGE_NODE_FALLBACK = """
UNWIND $rows AS row
MERGE (n:GraphNode {key: row.key})
SET n += row.properties, n.label = row.label
RETURN count(n) AS created
"""

MERGE_EDGE_FALLBACK = """
UNWIND $rows AS row
MATCH (a:GraphNode {key: row.source})
MATCH (b:GraphNode {key: row.target})
CALL apoc.merge.relationship(a, row.type, {}, row.properties, b, {}) YIELD rel
RETURN count(rel) AS created
"""

# --- queries -----------------------------------------------------------------

LIST_EXERCISES = """
MATCH (e:GraphNode {label: 'Exercise'})
RETURN e.key AS key, properties(e) AS props
"""

EXERCISE_REQUIRED_EQUIPMENT = """
MATCH (e:GraphNode {key: $exercise_key})-[:REQUIRES]->(q:GraphNode)
RETURN q.name AS name
"""

EXERCISE_PATTERNS = """
MATCH (e:GraphNode {key: $exercise_key})-[:HAS_PATTERN]->(p:GraphNode)
RETURN p.name AS name
"""

EXERCISE_STRESSED_REGIONS = """
MATCH (e:GraphNode {key: $exercise_key})-[:STRESSES]->(a:GraphNode)
RETURN a.id AS id, a.name AS name
"""

MEMBER_EQUIPMENT = """
MATCH (m:GraphNode {key: $member_key})-[:HAS_EQUIPMENT]->(q:GraphNode)
RETURN q.name AS name
"""

# The anatomy walk, in both directions:
#   * upward  - an injury at the patellofemoral joint must reach exercises the
#               catalog annotates only as loading "knee";
#   * downward - an injury recorded at "knee" must cover its sub-structures.
ANATOMICAL_CLOSURE = """
MATCH (start:GraphNode {key: $region_key})
OPTIONAL MATCH (start)-[:PART_OF*0..6]->(up:GraphNode)
WITH start, collect(DISTINCT up.id) AS ancestors
OPTIONAL MATCH (down:GraphNode)-[:PART_OF*0..6]->(start)
WITH start, ancestors, collect(DISTINCT down.id) AS descendants
UNWIND (ancestors + descendants + [start.id]) AS id
WITH id WHERE id IS NOT NULL
RETURN DISTINCT id
"""

PART_OF_PATH = """
MATCH path = (a:GraphNode {key: $start_key})-[:PART_OF*1..6]->(b:GraphNode {key: $target_key})
RETURN [n IN nodes(path) | n.name] AS names
ORDER BY length(path) ASC
LIMIT 1
"""

STRESSES_PATH = """
MATCH (e:GraphNode {key: $exercise_key})-[:STRESSES]->(a:GraphNode {id: $region_id})
RETURN e.name AS exercise, a.name AS region
LIMIT 1
"""

# Member injury -> condition -> affected region, with the contraindicated
# movement patterns attached. This is the join between the two subgraphs.
INJURY_AFFECTED_REGIONS = """
MATCH (m:GraphNode {key: $member_key})-[:HAS_INJURY]->(i:GraphNode)
OPTIONAL MATCH (i)-[:MAPS_TO]->(c:GraphNode)
OPTIONAL MATCH (c)-[:AFFECTS]->(region:GraphNode)
OPTIONAL MATCH (i)-[:AFFECTS]->(direct:GraphNode)
OPTIONAL MATCH (c)-[:CONTRAINDICATES]->(p:GraphNode)
RETURN i.id AS injury_id,
       i.name AS injury_name,
       i.severity AS severity,
       i.status AS status,
       i.body_side AS body_side,
       i.notes AS notes,
       c.id AS condition_id,
       c.name AS condition_label,
       coalesce(region.id, direct.id) AS root_region,
       coalesce(region.name, direct.name) AS root_region_label,
       collect(DISTINCT p.name) AS contraindicated_patterns
"""

PATTERNS_IN_FAMILY = """
MATCH (p:GraphNode)-[:IN_FAMILY]->(f:GraphNode {key: $family_key})
RETURN p.name AS name
"""

EXERCISES_WITH_PATTERN = """
MATCH (e:GraphNode)-[:HAS_PATTERN]->(p:GraphNode {key: $pattern_key})
RETURN e.id AS id
"""

GRAPH_STATS = """
MATCH (n:GraphNode)
WITH n.label AS label, count(*) AS c
RETURN 'node:' + label AS key, c AS count
UNION ALL
MATCH ()-[r]->()
WITH type(r) AS t, count(*) AS c
RETURN 'edge:' + t AS key, c AS count
"""

EXERCISE_PROVENANCE = """
MATCH (e:GraphNode {key: $exercise_key})
OPTIONAL MATCH (e)-[:STRESSES]->(a:GraphNode)
OPTIONAL MATCH (a)-[:PART_OF*0..4]->(parent:GraphNode)
OPTIONAL MATCH (e)-[:REQUIRES]->(q:GraphNode)
OPTIONAL MATCH (e)-[:HAS_PATTERN]->(p:GraphNode)-[:IN_FAMILY]->(f:GraphNode)
OPTIONAL MATCH (e)-[:TARGETS]->(mu:GraphNode)
RETURN e.name AS exercise,
       collect(DISTINCT a.name) AS stresses,
       collect(DISTINCT parent.name) AS anatomy_ancestors,
       collect(DISTINCT q.name) AS requires,
       collect(DISTINCT p.name) AS patterns,
       collect(DISTINCT f.name) AS families,
       collect(DISTINCT mu.name) AS targets
"""
