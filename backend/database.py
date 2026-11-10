import sqlite3
import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from models import LogEventRequest

_UNSET = object()

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        data_root = Path(__file__).resolve().parent / "data"
        if db_path:
            resolved_path = db_path
        else:
            env_path = os.getenv("DATABASE_PATH")
            if env_path:
                resolved_path = env_path
            else:
                default_path = data_root / "unspecified_queries.db"
                legacy_path = data_root / "undspecified_queries.db"
                resolved_path = legacy_path if legacy_path.exists() else default_path
        self.db_path = str(Path(resolved_path).resolve())
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_database()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize the SQLite database with required tables."""
        conn = self._connect()
        cursor = conn.cursor()
        
        # Create events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create priors table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS priors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_signature TEXT UNIQUE NOT NULL,
                objective_id TEXT,
                common_facet_answers TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                objective_id TEXT,
                persona_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'draft',
                qmd_path TEXT NOT NULL,
                last_output_html_path TEXT,
                last_output_pdf_path TEXT,
                last_render_at DATETIME,
                content_hash TEXT,
                last_manifest_path TEXT,
                last_log_path TEXT,
                error_message TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS render_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                started_at DATETIME,
                finished_at DATETIME,
                params_json TEXT,
                engine TEXT DEFAULT 'python',
                output_formats TEXT,
                lock_owner TEXT,
                log_path TEXT,
                error_message TEXT,
                FOREIGN KEY(report_id) REFERENCES reports(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS personas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                scope TEXT NOT NULL,
                identity_key TEXT,
                source TEXT NOT NULL DEFAULT 'interviews',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                persona_json TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                last_summary TEXT NOT NULL DEFAULT ''
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                scope_id TEXT,
                end_product TEXT NOT NULL,
                target_host TEXT NOT NULL DEFAULT 'Saccharomyces cerevisiae',
                project_goal TEXT NOT NULL DEFAULT '',
                raw_material_focus TEXT,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                transcript_path TEXT,
                transcript_text TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata_json TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS persona_refactor_state (
                persona_id INTEGER PRIMARY KEY,
                last_event_id INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(persona_id) REFERENCES personas(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER,
                objective_id TEXT,
                query TEXT,
                response_text TEXT,
                rating INTEGER NOT NULL,
                feedback_text TEXT,
                metadata_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_workspace_state (
                project_id INTEGER NOT NULL,
                persona_id INTEGER NOT NULL,
                focus_question TEXT,
                clarifying_answers_json TEXT NOT NULL DEFAULT '{}',
                reasoning_notes TEXT,
                work_template_json TEXT,
                plan_json TEXT,
                selected_step_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (project_id, persona_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_query_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '',
                state_json TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_execution_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                persona_id INTEGER NOT NULL,
                run_kind TEXT NOT NULL DEFAULT 'agentic_execution',
                status TEXT NOT NULL DEFAULT 'queued',
                objective_id TEXT,
                mode_label TEXT,
                focus_question TEXT,
                current_stage TEXT,
                summary TEXT,
                error_message TEXT,
                input_json TEXT,
                final_work_template_json TEXT,
                final_plan_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                started_at DATETIME,
                finished_at DATETIME
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_execution_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                stage_key TEXT,
                title TEXT,
                detail TEXT,
                payload_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES project_execution_runs(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workspace_memory (
                workspace_key TEXT PRIMARY KEY,
                scope TEXT NOT NULL DEFAULT 'default',
                explicit_state TEXT NOT NULL DEFAULT '{}',
                tacit_state TEXT NOT NULL DEFAULT '[]',
                handoff_summary TEXT NOT NULL DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                model TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ontology_nodes (
                project_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                type TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                source_refs_json TEXT NOT NULL DEFAULT '[]',
                attributes_json TEXT NOT NULL DEFAULT '{}',
                confidence REAL NOT NULL DEFAULT 0.7,
                status TEXT NOT NULL DEFAULT 'inferred',
                generated_by TEXT NOT NULL DEFAULT 'system',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (project_id, node_id),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ontology_edges (
                project_id INTEGER NOT NULL,
                edge_id TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0.7,
                status TEXT NOT NULL DEFAULT 'inferred',
                generated_by TEXT NOT NULL DEFAULT 'system',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (project_id, edge_id),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ontology_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                sync_source TEXT NOT NULL DEFAULT 'workbench',
                node_count INTEGER NOT NULL DEFAULT 0,
                edge_count INTEGER NOT NULL DEFAULT 0,
                input_summary TEXT NOT NULL DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_render_jobs_status_created
            ON render_jobs(status, created_at)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_personas_scope
            ON personas(scope)
        ''')

        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_scope
            ON projects(scope_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_projects_status_updated
            ON projects(status, updated_at)
        ''')

        try:
            cursor.execute("ALTER TABLE personas ADD COLUMN identity_key TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE personas ADD COLUMN project_id INTEGER")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE project_workspace_state ADD COLUMN reasoning_notes TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE project_workspace_state ADD COLUMN work_template_json TEXT")
        except sqlite3.OperationalError:
            pass

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_personas_scope_name_norm
            ON personas(lower(trim(scope)), lower(trim(name)))
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_personas_scope_identity
            ON personas(lower(trim(scope)), identity_key)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_interviews_scope
            ON interviews(scope)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_personas_project_id
            ON personas(project_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_project_workspace_project_persona
            ON project_workspace_state(project_id, persona_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_project_query_sessions_project_updated
            ON project_query_sessions(project_id, updated_at DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_project_execution_runs_project_persona
            ON project_execution_runs(project_id, persona_id, updated_at DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_project_execution_runs_status
            ON project_execution_runs(status, updated_at DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_project_execution_events_run
            ON project_execution_events(run_id, id ASC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_workspace_memory_scope_updated
            ON workspace_memory(scope, updated_at)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_llm_cache_task_updated
            ON llm_cache(task_type, updated_at DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ontology_nodes_project_type
            ON ontology_nodes(project_id, type, updated_at DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ontology_edges_project_relation
            ON ontology_edges(project_id, relation, updated_at DESC)
        ''')
        
        conn.commit()
        conn.close()
    
    def log_event(self, event_request: LogEventRequest):
        """Log an event to the database."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO events (event_type, payload)
            VALUES (?, ?)
        ''', (event_request.event_type, json.dumps(event_request.payload)))
        
        conn.commit()
        conn.close()

    def list_events(self, min_id: int = 0, limit: int = 500) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, event_type, payload, timestamp
            FROM events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            ''',
            (min_id, limit),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["payload"] = json.loads(row.get("payload") or "{}")
        return rows

    def list_project_events(self, project_id: int, limit: int = 1000) -> List[Dict[str, Any]]:
        rows = self.list_events(min_id=0, limit=max(limit * 3, limit))
        filtered: List[Dict[str, Any]] = []
        for row in rows:
            payload = row.get("payload") or {}
            try:
                payload_project_id = int(payload.get("project_id") or 0)
            except Exception:
                payload_project_id = 0
            if payload_project_id == int(project_id):
                filtered.append(row)
            if len(filtered) >= limit:
                break
        return filtered

    def get_persona_refactor_checkpoint(self, persona_id: int) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT last_event_id FROM persona_refactor_state WHERE persona_id = ?',
            (persona_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return 0
        return int(row[0] or 0)

    def set_persona_refactor_checkpoint(self, persona_id: int, last_event_id: int):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO persona_refactor_state(persona_id, last_event_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(persona_id)
            DO UPDATE SET last_event_id=excluded.last_event_id, updated_at=CURRENT_TIMESTAMP
            ''',
            (persona_id, last_event_id),
        )
        conn.commit()
        conn.close()

    def create_feedback(
        self,
        persona_id: Optional[int],
        objective_id: Optional[str],
        query: Optional[str],
        response_text: Optional[str],
        rating: int,
        feedback_text: Optional[str],
        metadata: Dict[str, Any],
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO feedback (persona_id, objective_id, query, response_text, rating, feedback_text, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (persona_id, objective_id, query, response_text, rating, feedback_text, json.dumps(metadata or {})),
        )
        feedback_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return int(feedback_id)

    def list_feedback(self, persona_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        if persona_id is None:
            cursor.execute(
                '''
                SELECT * FROM feedback
                ORDER BY id DESC
                LIMIT ?
                ''',
                (limit,),
            )
        else:
            cursor.execute(
                '''
                SELECT * FROM feedback
                WHERE persona_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (persona_id, limit),
            )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["metadata_json"] = json.loads(row.get("metadata_json") or "{}")
        return rows
    def get_prior(self, query_signature: str) -> Optional[Dict[str, Any]]:
        """Retrieve prior information for a query signature."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT objective_id, common_facet_answers
            FROM priors
            WHERE query_signature = ?
        ''', (query_signature,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            objective_id, common_facet_answers = result[0], result[1]
            return {
                "objective_id": objective_id,
                "common_facet_answers": json.loads(common_facet_answers) if common_facet_answers else {}
            }
        return None
    
    def update_prior(self, query_signature: str, objective_id: str, facet_answers: Dict[str, str]):
        """Update prior information for a query signature."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO priors (query_signature, objective_id, common_facet_answers, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (query_signature, objective_id, json.dumps(facet_answers), datetime.now()))
        
        conn.commit()
        conn.close()
    
    def query_signature(self, query: str) -> str:
        """Generate a simple hash signature for a query."""
        return hashlib.md5(query.lower().strip().encode()).hexdigest()[:16]

    def llm_cache_key(self, task_type: str, inputs: Dict[str, Any]) -> str:
        """Generate a stable cache key for deterministic LLM tasks."""
        normalized = json.dumps(
            {"task_type": task_type, "inputs": inputs},
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get_llm_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM llm_cache WHERE cache_key = ?', (cache_key,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        data = dict(row)
        try:
            data["payload"] = json.loads(data.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            data["payload"] = {}
        try:
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            data["metadata"] = {}
        return data

    def upsert_llm_cache(
        self,
        *,
        cache_key: str,
        task_type: str,
        model: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO llm_cache (cache_key, task_type, model, payload_json, metadata_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                task_type = excluded.task_type,
                model = excluded.model,
                payload_json = excluded.payload_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            ''',
            (
                cache_key,
                task_type,
                model,
                json.dumps(payload),
                json.dumps(metadata or {}),
                datetime.now(),
            ),
        )
        conn.commit()
        conn.close()

    def get_workspace_memory(self, workspace_key: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM workspace_memory WHERE workspace_key = ?', (workspace_key,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        data = dict(row)
        data["explicit_state"] = json.loads(data.get("explicit_state") or "{}")
        data["tacit_state"] = json.loads(data.get("tacit_state") or "[]")
        return data

    def upsert_workspace_memory(
        self,
        workspace_key: str,
        scope: str,
        explicit_state: Dict[str, Any],
        tacit_state: List[Dict[str, Any]],
        handoff_summary: str = "",
    ) -> Dict[str, Any]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO workspace_memory (workspace_key, scope, explicit_state, tacit_state, handoff_summary, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(workspace_key) DO UPDATE SET
                scope = excluded.scope,
                explicit_state = excluded.explicit_state,
                tacit_state = excluded.tacit_state,
                handoff_summary = excluded.handoff_summary,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (
                workspace_key,
                scope,
                json.dumps(explicit_state),
                json.dumps(tacit_state),
                handoff_summary,
            ),
        )
        conn.commit()
        conn.close()
        return self.get_workspace_memory(workspace_key) or {
            "workspace_key": workspace_key,
            "scope": scope,
            "explicit_state": explicit_state,
            "tacit_state": tacit_state,
            "handoff_summary": handoff_summary,
            "updated_at": None,
        }

    def _hydrate_ontology_node(self, row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["id"] = payload.pop("node_id")
        payload["source_refs"] = json.loads(payload.pop("source_refs_json") or "[]")
        payload["attributes"] = json.loads(payload.pop("attributes_json") or "{}")
        payload.pop("project_id", None)
        payload.pop("generated_by", None)
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return payload

    def _hydrate_ontology_edge(self, row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["id"] = payload.pop("edge_id")
        payload["source"] = payload.pop("source_node_id")
        payload["target"] = payload.pop("target_node_id")
        payload["evidence"] = json.loads(payload.pop("evidence_json") or "[]")
        payload.pop("project_id", None)
        payload.pop("generated_by", None)
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return payload

    def get_project_ontology(self, project_id: int) -> Dict[str, Any]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM ontology_nodes
            WHERE project_id = ?
            ORDER BY
                CASE status WHEN 'confirmed' THEN 0 WHEN 'edited' THEN 1 WHEN 'inferred' THEN 2 ELSE 3 END,
                updated_at DESC,
                label ASC
            ''',
            (project_id,),
        )
        nodes = [self._hydrate_ontology_node(row) for row in cursor.fetchall()]
        cursor.execute(
            '''
            SELECT * FROM ontology_edges
            WHERE project_id = ?
            ORDER BY
                CASE status WHEN 'confirmed' THEN 0 WHEN 'edited' THEN 1 WHEN 'inferred' THEN 2 ELSE 3 END,
                updated_at DESC,
                relation ASC
            ''',
            (project_id,),
        )
        edges = [self._hydrate_ontology_edge(row) for row in cursor.fetchall()]
        cursor.execute(
            '''
            SELECT created_at FROM ontology_sync_runs
            WHERE project_id = ?
            ORDER BY id DESC
            LIMIT 1
            ''',
            (project_id,),
        )
        sync_row = cursor.fetchone()
        conn.close()
        return {
            "nodes": nodes,
            "edges": edges,
            "last_synced_at": sync_row["created_at"] if sync_row else None,
        }

    def upsert_project_ontology(
        self,
        project_id: int,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        sync_source: str = "workbench",
        input_summary: str = "",
        replace_generated: bool = False,
    ) -> Dict[str, Any]:
        conn = self._connect()
        cursor = conn.cursor()
        if replace_generated:
            cursor.execute(
                "DELETE FROM ontology_edges WHERE project_id = ? AND generated_by = ? AND status = 'inferred'",
                (project_id, sync_source),
            )
            cursor.execute(
                "DELETE FROM ontology_nodes WHERE project_id = ? AND generated_by = ? AND status = 'inferred'",
                (project_id, sync_source),
            )
        for node in nodes:
            cursor.execute(
                '''
                INSERT INTO ontology_nodes (
                    project_id, node_id, type, label, description, source_refs_json,
                    attributes_json, confidence, status, generated_by, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(project_id, node_id) DO UPDATE SET
                    type = excluded.type,
                    label = excluded.label,
                    description = excluded.description,
                    source_refs_json = excluded.source_refs_json,
                    attributes_json = excluded.attributes_json,
                    confidence = max(ontology_nodes.confidence, excluded.confidence),
                    status = CASE
                        WHEN ontology_nodes.status IN ('confirmed', 'rejected', 'edited') THEN ontology_nodes.status
                        ELSE excluded.status
                    END,
                    generated_by = excluded.generated_by,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (
                    project_id,
                    node.get("id"),
                    node.get("type") or "concept",
                    node.get("label") or node.get("id") or "Untitled",
                    node.get("description") or "",
                    json.dumps(node.get("source_refs") or []),
                    json.dumps(node.get("attributes") or {}),
                    float(node.get("confidence") or 0.7),
                    node.get("status") or "inferred",
                    sync_source,
                ),
            )

        for edge in edges:
            cursor.execute(
                '''
                INSERT INTO ontology_edges (
                    project_id, edge_id, source_node_id, target_node_id, relation,
                    evidence_json, confidence, status, generated_by, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(project_id, edge_id) DO UPDATE SET
                    source_node_id = excluded.source_node_id,
                    target_node_id = excluded.target_node_id,
                    relation = excluded.relation,
                    evidence_json = excluded.evidence_json,
                    confidence = max(ontology_edges.confidence, excluded.confidence),
                    status = CASE
                        WHEN ontology_edges.status IN ('confirmed', 'rejected', 'edited') THEN ontology_edges.status
                        ELSE excluded.status
                    END,
                    generated_by = excluded.generated_by,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (
                    project_id,
                    edge.get("id"),
                    edge.get("source"),
                    edge.get("target"),
                    edge.get("relation") or "related_to",
                    json.dumps(edge.get("evidence") or []),
                    float(edge.get("confidence") or 0.7),
                    edge.get("status") or "inferred",
                    sync_source,
                ),
            )

        cursor.execute(
            '''
            INSERT INTO ontology_sync_runs(project_id, sync_source, node_count, edge_count, input_summary)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (project_id, sync_source, len(nodes), len(edges), input_summary[:1000]),
        )
        conn.commit()
        conn.close()
        return self.get_project_ontology(project_id)

    def update_ontology_status(
        self,
        project_id: int,
        target_type: str,
        target_id: str,
        status: str,
        reviewer_note: Optional[str] = None,
    ) -> bool:
        conn = self._connect()
        cursor = conn.cursor()
        if target_type == "node":
            row = cursor.execute(
                'SELECT attributes_json FROM ontology_nodes WHERE project_id = ? AND node_id = ?',
                (project_id, target_id),
            ).fetchone()
            if not row:
                conn.close()
                return False
            attributes = json.loads(row["attributes_json"] or "{}")
            if reviewer_note is not None:
                attributes["reviewer_note"] = reviewer_note
            cursor.execute(
                '''
                UPDATE ontology_nodes
                SET status = ?, attributes_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND node_id = ?
                ''',
                (status, json.dumps(attributes), project_id, target_id),
            )
        else:
            cursor.execute(
                '''
                UPDATE ontology_edges
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND edge_id = ?
                ''',
                (status, project_id, target_id),
            )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def create_report(self, title: str, qmd_path: str, objective_id: Optional[str] = None) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO reports (title, objective_id, qmd_path, status, content_hash)
            VALUES (?, ?, ?, 'draft', '')
            ''',
            (title, objective_id, qmd_path),
        )
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return int(report_id)

    def get_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reports WHERE id = ?', (report_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_reports_for_objective(self, objective_id: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reports WHERE objective_id = ? ORDER BY updated_at DESC', (objective_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def list_reports(self, objective_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        if objective_id:
            cursor.execute('SELECT * FROM reports WHERE objective_id = ? ORDER BY updated_at DESC', (objective_id,))
        else:
            cursor.execute('SELECT * FROM reports ORDER BY updated_at DESC')
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def update_report_qmd(self, report_id: int, content_hash: str):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE reports
            SET content_hash = ?, updated_at = CURRENT_TIMESTAMP, status = 'draft', error_message = NULL
            WHERE id = ?
            ''',
            (content_hash, report_id),
        )
        conn.commit()
        conn.close()

    def set_report_qmd_path(self, report_id: int, qmd_path: str):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE reports
            SET qmd_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (qmd_path, report_id),
        )
        conn.commit()
        conn.close()

    def update_report_status(
        self,
        report_id: int,
        status: str,
        error_message: Optional[str] = None,
        persona_id: Optional[int] = None,
    ):
        conn = self._connect()
        cursor = conn.cursor()
        if persona_id is None:
            cursor.execute(
                '''
                UPDATE reports
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (status, error_message, report_id),
            )
        else:
            cursor.execute(
                '''
                UPDATE reports
                SET status = ?, error_message = ?, persona_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (status, error_message, persona_id, report_id),
            )
        conn.commit()
        conn.close()

    def update_report_render_result(
        self,
        report_id: int,
        html_path: Optional[str],
        pdf_path: Optional[str],
        manifest_path: str,
        log_path: str,
        status: str,
        error_message: Optional[str] = None,
    ):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE reports
            SET status = ?,
                last_output_html_path = COALESCE(?, last_output_html_path),
                last_output_pdf_path = COALESCE(?, last_output_pdf_path),
                last_manifest_path = ?,
                last_log_path = ?,
                last_render_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                error_message = ?
            WHERE id = ?
            ''',
            (status, html_path, pdf_path, manifest_path, log_path, error_message, report_id),
        )
        conn.commit()
        conn.close()

    def enqueue_render_job(
        self,
        report_id: int,
        params: Dict[str, Any],
        output_formats: List[str],
        engine: str = "python",
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO render_jobs (report_id, status, params_json, output_formats, engine)
            VALUES (?, 'queued', ?, ?, ?)
            ''',
            (report_id, json.dumps(params), json.dumps(output_formats), engine),
        )
        job_id = cursor.lastrowid
        cursor.execute(
            '''
            UPDATE reports SET status='queued', updated_at=CURRENT_TIMESTAMP, error_message=NULL WHERE id=?
            ''',
            (report_id,),
        )
        conn.commit()
        conn.close()
        return int(job_id)

    def get_latest_render_job_for_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM render_jobs
            WHERE report_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            ''',
            (report_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def claim_next_render_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            '''
            SELECT * FROM render_jobs
            WHERE status='queued'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            '''
        )
        row = cursor.fetchone()
        if not row:
            conn.commit()
            conn.close()
            return None

        job_id = row["id"]
        cursor.execute(
            '''
            UPDATE render_jobs
            SET status='running', started_at=CURRENT_TIMESTAMP, lock_owner=?
            WHERE id=? AND status='queued'
            ''',
            (worker_id, job_id),
        )
        if cursor.rowcount != 1:
            conn.commit()
            conn.close()
            return None

        cursor.execute(
            '''
            UPDATE reports
            SET status='running', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            ''',
            (row["report_id"],),
        )
        conn.commit()
        cursor.execute('SELECT * FROM render_jobs WHERE id = ?', (job_id,))
        claimed = cursor.fetchone()
        conn.close()
        return dict(claimed) if claimed else None

    def update_render_job_result(self, job_id: int, status: str, log_path: str, error_message: Optional[str] = None):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE render_jobs
            SET status=?, finished_at=CURRENT_TIMESTAMP, log_path=?, error_message=?
            WHERE id=?
            ''',
            (status, log_path, error_message, job_id),
        )
        conn.commit()
        conn.close()

    def create_interview(
        self,
        scope: str,
        transcript_text: Optional[str],
        transcript_path: Optional[str],
        metadata_json: Dict[str, Any],
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO interviews (scope, transcript_path, transcript_text, metadata_json)
            VALUES (?, ?, ?, ?)
            ''',
            (scope, transcript_path, transcript_text, json.dumps(metadata_json)),
        )
        interview_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return int(interview_id)

    def create_project(
        self,
        name: str,
        end_product: str,
        target_host: str,
        project_goal: str,
        raw_material_focus: Optional[str] = None,
        notes: Optional[str] = None,
        status: str = "active",
        scope_id: Optional[str] = None,
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO projects (name, scope_id, end_product, target_host, project_goal, raw_material_focus, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (name, scope_id, end_product, target_host, project_goal, raw_material_focus, notes, status),
        )
        project_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return int(project_id)

    def update_project_scope(self, project_id: int, scope_id: str):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE projects
            SET scope_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (scope_id, project_id),
        )
        conn.commit()
        conn.close()

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_projects(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        if status:
            cursor.execute('SELECT * FROM projects WHERE status = ? ORDER BY updated_at DESC, id DESC', (status,))
        else:
            cursor.execute('SELECT * FROM projects ORDER BY updated_at DESC, id DESC')
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def delete_project(self, project_id: int) -> bool:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM personas WHERE project_id = ?', (project_id,))
        persona_ids = [int(r[0]) for r in cursor.fetchall()]

        if persona_ids:
            placeholders = ','.join(['?' for _ in persona_ids])
            cursor.execute(f'DELETE FROM persona_refactor_state WHERE persona_id IN ({placeholders})', persona_ids)
            cursor.execute(f'DELETE FROM feedback WHERE persona_id IN ({placeholders})', persona_ids)
            cursor.execute(f'DELETE FROM project_workspace_state WHERE persona_id IN ({placeholders})', persona_ids)
            cursor.execute(f'DELETE FROM personas WHERE id IN ({placeholders})', persona_ids)

        cursor.execute('DELETE FROM project_workspace_state WHERE project_id = ?', (project_id,))
        cursor.execute('DELETE FROM project_query_sessions WHERE project_id = ?', (project_id,))
        cursor.execute('DELETE FROM ontology_edges WHERE project_id = ?', (project_id,))
        cursor.execute('DELETE FROM ontology_nodes WHERE project_id = ?', (project_id,))
        cursor.execute('DELETE FROM ontology_sync_runs WHERE project_id = ?', (project_id,))
        cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def list_project_query_sessions(self, project_id: int) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM project_query_sessions
            WHERE project_id = ?
            ORDER BY updated_at DESC, id DESC
            ''',
            (project_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["state"] = json.loads(row.get("state_json") or "{}")
        return rows

    def get_project_query_session(self, query_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM project_query_sessions WHERE id = ?', (query_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["state"] = json.loads(payload.get("state_json") or "{}")
        return payload

    def create_project_query_session(self, project_id: int, title: str, query: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO project_query_sessions(project_id, title, query, state_json)
            VALUES (?, ?, ?, ?)
            ''',
            (project_id, title, query, json.dumps(state or {})),
        )
        query_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        created = self.get_project_query_session(query_id)
        return created or {}

    def update_project_query_session(
        self,
        query_id: int,
        *,
        title: Optional[str] = None,
        query: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        existing = self.get_project_query_session(query_id)
        if not existing:
            return None
        next_title = existing.get("title") if title is None else title
        next_query = existing.get("query") if query is None else query
        next_state = existing.get("state") if state is None else state
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE project_query_sessions
            SET title = ?, query = ?, state_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (next_title, next_query, json.dumps(next_state or {}), query_id),
        )
        conn.commit()
        conn.close()
        return self.get_project_query_session(query_id)

    def get_project_workspace_state(self, project_id: int, persona_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM project_workspace_state
            WHERE project_id = ? AND persona_id = ?
            ''',
            (project_id, persona_id),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["clarifying_answers"] = json.loads(payload.get("clarifying_answers_json") or "{}")
        payload["work_template"] = json.loads(payload.get("work_template_json") or "null")
        payload["plan"] = json.loads(payload.get("plan_json") or "null")
        return payload

    def upsert_project_workspace_state(
        self,
        project_id: int,
        persona_id: int,
        focus_question: Optional[str],
        clarifying_answers: Dict[str, Any],
        reasoning_notes: Optional[str],
        work_template: Optional[Dict[str, Any]],
        plan: Optional[Dict[str, Any]],
        selected_step_id: Optional[str],
    ) -> Dict[str, Any]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO project_workspace_state (
                project_id, persona_id, focus_question, clarifying_answers_json, reasoning_notes, work_template_json, plan_json, selected_step_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(project_id, persona_id)
            DO UPDATE SET
                focus_question=excluded.focus_question,
                clarifying_answers_json=excluded.clarifying_answers_json,
                reasoning_notes=excluded.reasoning_notes,
                work_template_json=excluded.work_template_json,
                plan_json=excluded.plan_json,
                selected_step_id=excluded.selected_step_id,
                updated_at=CURRENT_TIMESTAMP
            ''',
            (
                project_id,
                persona_id,
                focus_question,
                json.dumps(clarifying_answers or {}),
                reasoning_notes,
                json.dumps(work_template) if work_template is not None else None,
                json.dumps(plan) if plan is not None else None,
                selected_step_id,
            ),
        )
        conn.commit()
        conn.close()
        state = self.get_project_workspace_state(project_id, persona_id)
        if not state:
            raise RuntimeError("Failed to persist project workspace state")
        return state

    def _hydrate_project_execution_run(self, row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["input"] = json.loads(payload.get("input_json") or "{}")
        payload["final_work_template"] = json.loads(payload.get("final_work_template_json") or "null")
        payload["final_plan"] = json.loads(payload.get("final_plan_json") or "null")
        return payload

    def create_project_execution_run(
        self,
        *,
        project_id: int,
        persona_id: int,
        run_kind: str,
        objective_id: Optional[str],
        mode_label: Optional[str],
        focus_question: Optional[str],
        input_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO project_execution_runs (
                project_id, persona_id, run_kind, status, objective_id, mode_label, focus_question, input_json
            )
            VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)
            ''',
            (
                project_id,
                persona_id,
                run_kind,
                objective_id,
                mode_label,
                focus_question,
                json.dumps(input_payload or {}),
            ),
        )
        run_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        row = self.get_project_execution_run(run_id)
        if not row:
            raise RuntimeError("Failed to create execution run")
        return row

    def get_project_execution_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM project_execution_runs WHERE id = ?', (run_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._hydrate_project_execution_run(row)

    def get_latest_project_execution_run(self, project_id: int, persona_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM project_execution_runs
            WHERE project_id = ? AND persona_id = ?
            ORDER BY id DESC
            LIMIT 1
            ''',
            (project_id, persona_id),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._hydrate_project_execution_run(row)

    def list_project_execution_events(self, run_id: int, after_id: int = 0) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM project_execution_events
            WHERE run_id = ? AND id > ?
            ORDER BY id ASC
            ''',
            (run_id, after_id),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["payload"] = json.loads(row.get("payload_json") or "{}")
        return rows

    def append_project_execution_event(
        self,
        *,
        run_id: int,
        event_type: str,
        stage_key: Optional[str],
        title: str,
        detail: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO project_execution_events (run_id, event_type, stage_key, title, detail, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (run_id, event_type, stage_key, title, detail, json.dumps(payload or {})),
        )
        event_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        return event_id

    def update_project_execution_run(
        self,
        run_id: int,
        *,
        status: Any = _UNSET,
        current_stage: Any = _UNSET,
        summary: Any = _UNSET,
        error_message: Any = _UNSET,
        final_work_template: Any = _UNSET,
        final_plan: Any = _UNSET,
        set_started: bool = False,
        set_finished: bool = False,
    ) -> Dict[str, Any]:
        assignments: List[str] = []
        params: List[Any] = []

        if status is not _UNSET:
            assignments.append("status = ?")
            params.append(status)
        if current_stage is not _UNSET:
            assignments.append("current_stage = ?")
            params.append(current_stage)
        if summary is not _UNSET:
            assignments.append("summary = ?")
            params.append(summary)
        if error_message is not _UNSET:
            assignments.append("error_message = ?")
            params.append(error_message)
        if final_work_template is not _UNSET:
            assignments.append("final_work_template_json = ?")
            params.append(json.dumps(final_work_template) if final_work_template is not None else None)
        if final_plan is not _UNSET:
            assignments.append("final_plan_json = ?")
            params.append(json.dumps(final_plan) if final_plan is not None else None)
        if set_started:
            assignments.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
        if set_finished:
            assignments.append("finished_at = CURRENT_TIMESTAMP")

        assignments.append("updated_at = CURRENT_TIMESTAMP")

        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            f'''
            UPDATE project_execution_runs
            SET {", ".join(assignments)}
            WHERE id = ?
            ''',
            (*params, run_id),
        )
        conn.commit()
        conn.close()
        row = self.get_project_execution_run(run_id)
        if not row:
            raise RuntimeError("Failed to update execution run")
        return row

    def mark_incomplete_execution_runs_failed(self, message: str):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE project_execution_runs
            SET status = 'failed',
                error_message = COALESCE(error_message, ?),
                finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('queued', 'running')
            ''',
            (message,),
        )
        conn.commit()
        conn.close()

    def get_interview_by_scope_path(self, scope: str, transcript_path: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM interviews
            WHERE scope = ? AND transcript_path = ?
            ORDER BY id DESC
            LIMIT 1
            ''',
            (scope, transcript_path),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["metadata_json"] = json.loads(payload.get("metadata_json") or "{}")
        return payload

    def get_interviews(self, scope: str, interview_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        if interview_ids:
            placeholders = ",".join(["?" for _ in interview_ids])
            cursor.execute(
                f'''
                SELECT * FROM interviews WHERE scope = ? AND id IN ({placeholders}) ORDER BY created_at ASC
                ''',
                [scope, *interview_ids],
            )
        else:
            cursor.execute('SELECT * FROM interviews WHERE scope = ? ORDER BY created_at ASC', (scope,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["metadata_json"] = json.loads(row.get("metadata_json") or "{}")
        return rows

    def create_persona(
        self,
        name: str,
        scope: str,
        persona_json: Dict[str, Any],
        last_summary: str,
        identity_key: Optional[str] = None,
        version: Optional[int] = None,
        source: str = "interviews",
        project_id: Optional[int] = None,
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        final_version = version if version is not None else 1
        cursor.execute(
            '''
            INSERT INTO personas (name, scope, identity_key, source, persona_json, version, last_summary, project_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (name, scope, identity_key, source, json.dumps(persona_json), final_version, last_summary, project_id),
        )
        persona_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return int(persona_id)

    def update_persona(
        self,
        persona_id: int,
        persona_json: Dict[str, Any],
        last_summary: str,
        name: Optional[str] = None,
        identity_key: Optional[str] = None,
    ):
        conn = self._connect()
        cursor = conn.cursor()
        if name:
            if identity_key is None:
                cursor.execute(
                    '''
                    UPDATE personas
                    SET name=?, persona_json=?, last_summary=?, version=version+1, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    ''',
                    (name, json.dumps(persona_json), last_summary, persona_id),
                )
            else:
                cursor.execute(
                    '''
                    UPDATE personas
                    SET name=?, identity_key=?, persona_json=?, last_summary=?, version=version+1, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    ''',
                    (name, identity_key, json.dumps(persona_json), last_summary, persona_id),
                )
        else:
            if identity_key is None:
                cursor.execute(
                    '''
                    UPDATE personas
                    SET persona_json=?, last_summary=?, version=version+1, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    ''',
                    (json.dumps(persona_json), last_summary, persona_id),
                )
            else:
                cursor.execute(
                    '''
                    UPDATE personas
                    SET identity_key=?, persona_json=?, last_summary=?, version=version+1, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    ''',
                    (identity_key, json.dumps(persona_json), last_summary, persona_id),
                )
        conn.commit()
        conn.close()

    def get_persona(self, persona_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM personas WHERE id=?', (persona_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["persona_json"] = json.loads(payload.get("persona_json") or "{}")
        return payload

    def get_persona_by_scope_name(self, scope: str, name: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM personas
            WHERE scope = ? AND name = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            ''',
            (scope, name),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["persona_json"] = json.loads(payload.get("persona_json") or "{}")
        return payload

    def get_persona_by_scope_name_normalized(self, scope: str, name: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM personas
            WHERE lower(trim(scope)) = lower(trim(?))
              AND lower(trim(name)) = lower(trim(?))
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            ''',
            (scope, name),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["persona_json"] = json.loads(payload.get("persona_json") or "{}")
        return payload

    def get_persona_by_scope_identity(self, scope: str, identity_key: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM personas
            WHERE lower(trim(scope)) = lower(trim(?))
              AND identity_key = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            ''',
            (scope, identity_key),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["persona_json"] = json.loads(payload.get("persona_json") or "{}")
        return payload

    def list_personas_by_scope_identity(self, scope: str, identity_key: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM personas
            WHERE lower(trim(scope)) = lower(trim(?))
              AND identity_key = ?
            ORDER BY updated_at DESC, id DESC
            ''',
            (scope, identity_key),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["persona_json"] = json.loads(row.get("persona_json") or "{}")
        return rows

    def list_personas_by_scope_name_normalized(self, scope: str, name: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM personas
            WHERE lower(trim(scope)) = lower(trim(?))
              AND lower(trim(name)) = lower(trim(?))
            ORDER BY updated_at DESC, id DESC
            ''',
            (scope, name),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["persona_json"] = json.loads(row.get("persona_json") or "{}")
        return rows

    def delete_persona(self, persona_id: int):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM project_workspace_state WHERE persona_id = ?', (persona_id,))
        cursor.execute('DELETE FROM personas WHERE id = ?', (persona_id,))
        conn.commit()
        conn.close()

    def clear_personas(self, scope: Optional[str] = None) -> int:
        conn = self._connect()
        cursor = conn.cursor()

        if scope:
            cursor.execute('SELECT id FROM personas WHERE scope = ?', (scope,))
        else:
            cursor.execute('SELECT id FROM personas')
        persona_ids = [int(r[0]) for r in cursor.fetchall()]

        if not persona_ids:
            conn.close()
            return 0

        placeholders = ','.join(['?' for _ in persona_ids])
        cursor.execute(f'DELETE FROM persona_refactor_state WHERE persona_id IN ({placeholders})', persona_ids)
        cursor.execute(f'DELETE FROM feedback WHERE persona_id IN ({placeholders})', persona_ids)
        cursor.execute(f'DELETE FROM project_workspace_state WHERE persona_id IN ({placeholders})', persona_ids)
        cursor.execute(f'DELETE FROM personas WHERE id IN ({placeholders})', persona_ids)

        conn.commit()
        conn.close()
        return len(persona_ids)
    def list_personas(self, scope: Optional[str] = None, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn = self._connect()
        cursor = conn.cursor()
        if project_id is not None:
            cursor.execute('SELECT * FROM personas WHERE project_id=? ORDER BY updated_at DESC', (project_id,))
        elif scope:
            cursor.execute('SELECT * FROM personas WHERE scope=? ORDER BY updated_at DESC', (scope,))
        else:
            cursor.execute('SELECT * FROM personas ORDER BY updated_at DESC')
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["persona_json"] = json.loads(row.get("persona_json") or "{}")
        return rows

# Global database instance
db = DatabaseManager()
