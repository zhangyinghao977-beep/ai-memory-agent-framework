"""全部表结构集中在这里（2026-10-27 按名词解释 v0.14 重排）。

经验、记忆、知识包、记忆边界阀、事件链 AST、计算经历和修正记录互相引用，所以表放在同一个库、一次建好，外键才能成立。
旧版（10-26）的库用的是 `events` 表，与本结构不兼容；旧实验目录已停用，不做迁移。
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS contents (
    content_hash TEXT PRIMARY KEY,
    content TEXT NOT NULL
);

-- 经验／溯源记录（experience.py）：每一次发生或接收。不是形成后的记忆。
CREATE TABLE IF NOT EXISTS experiences (
    experience_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    content_hash TEXT NOT NULL REFERENCES contents(content_hash),
    origin TEXT NOT NULL,
    occurred_at TEXT,              -- 事件发生时间（由调用方给出，可能未知）
    recorded_at TEXT NOT NULL,     -- 登记时间（系统时钟）；v0.15：发生时间、登记时间与版本号不能互相冒充
    position_json TEXT,
    binding_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_experiences_chain ON experiences(chain_id, experience_id);
CREATE TABLE IF NOT EXISTS experience_links (
    experience_id INTEGER NOT NULL REFERENCES experiences(experience_id),
    target_experience_id INTEGER NOT NULL REFERENCES experiences(experience_id),
    relation TEXT NOT NULL,
    PRIMARY KEY (experience_id, target_experience_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_experience_links_target ON experience_links(target_experience_id, relation);
CREATE TABLE IF NOT EXISTS experience_package_refs (
    experience_id INTEGER NOT NULL REFERENCES experiences(experience_id),
    package_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    use TEXT NOT NULL,
    PRIMARY KEY (experience_id, package_id, version, use),
    FOREIGN KEY (package_id, version) REFERENCES package_versions(package_id, version)
);
CREATE INDEX IF NOT EXISTS idx_experience_package_refs ON experience_package_refs(package_id, version);
CREATE TABLE IF NOT EXISTS verifications (
    verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL REFERENCES experiences(experience_id),
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    note TEXT NOT NULL
);

-- 形成后的记忆（memory.py）：经验经拆解学习形成，或由知识形成（想象力）。
CREATE TABLE IF NOT EXISTS memory_items (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_kind TEXT NOT NULL CHECK (origin_kind IN ('LEARNED', 'IMAGINATION')),
    content_hash TEXT NOT NULL REFERENCES contents(content_hash),
    formation_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    revises_memory_id INTEGER REFERENCES memory_items(memory_id),  -- v0.17：修订是承接原版的新版本
    worlds_json TEXT NOT NULL,      -- v0.17：适用范围在形成时确定；空列表＝没说明，默认物理世界
    conditions_json TEXT,           -- v0.17：条件
    bindings_json TEXT,             -- v0.17：绑定（只能指向不会变的对象：素材、包的某个版本、经验、记忆）
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_experience_sources (
    memory_id INTEGER NOT NULL REFERENCES memory_items(memory_id),
    experience_id INTEGER NOT NULL REFERENCES experiences(experience_id),
    PRIMARY KEY (memory_id, experience_id)
);
CREATE TABLE IF NOT EXISTS memory_package_sources (
    memory_id INTEGER NOT NULL REFERENCES memory_items(memory_id),
    package_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (memory_id, package_id, version),
    FOREIGN KEY (package_id, version) REFERENCES package_versions(package_id, version)
);
CREATE TABLE IF NOT EXISTS memory_memory_sources (
    memory_id INTEGER NOT NULL REFERENCES memory_items(memory_id),
    source_memory_id INTEGER NOT NULL REFERENCES memory_items(memory_id),
    PRIMARY KEY (memory_id, source_memory_id)
);
CREATE TABLE IF NOT EXISTS recalls (
    experience_id INTEGER PRIMARY KEY REFERENCES experiences(experience_id),
    memory_id INTEGER NOT NULL REFERENCES memory_items(memory_id)
);
-- v0.17：遗忘与可达性另记，不改写记忆内容（不可篡改不等于不可遗忘）。
CREATE TABLE IF NOT EXISTS memory_reachability (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id INTEGER NOT NULL REFERENCES memory_items(memory_id),
    action TEXT NOT NULL CHECK (action IN ('FORGET', 'RESTORE')),
    basis_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

-- 学习材料库（learning_store.py，v0.16）：why 层学习 attention／映射函数用的材料。不是记忆，收录不等于证实。
-- 注意：这里的“学习材料条目”和知识库里的“素材”（materials 表）是两回事。
CREATE TABLE IF NOT EXISTS learning_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('memory', 'experience', 'call')),
    source_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    reason TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS training_runs (
    training_id INTEGER PRIMARY KEY AUTOINCREMENT,
    computation_id TEXT NOT NULL,
    parameter_version_json TEXT NOT NULL,
    purpose TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS training_run_items (
    training_id INTEGER NOT NULL REFERENCES training_runs(training_id),
    item_id INTEGER NOT NULL REFERENCES learning_items(item_id),
    PRIMARY KEY (training_id, item_id)
);

-- 知识库（registry.py）：知识包＝索引包。
CREATE TABLE IF NOT EXISTS materials (
    material_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('raw', 'method', 'package')),
    content_hash TEXT REFERENCES contents(content_hash),
    package_id TEXT
);
CREATE TABLE IF NOT EXISTS packages (
    package_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    reference_material_id TEXT NOT NULL REFERENCES materials(material_id),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'CROPPED')),
    origin_json TEXT NOT NULL,
    crop_json TEXT,
    round_id INTEGER REFERENCES formation_rounds(round_id),    -- B3：在哪一轮组合中形成
    home_cache_id INTEGER REFERENCES work_caches(cache_id)    -- B2：非空＝工作侧局部包，只在这个工作缓存里可用
);
-- B2：推广到全局、发布为可发布知识，都只追加记录。
CREATE TABLE IF NOT EXISTS package_events (
    package_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT NOT NULL REFERENCES packages(package_id),
    action TEXT NOT NULL CHECK (action IN ('PROMOTE', 'PUBLISH')),
    basis_json TEXT NOT NULL,
    regression_json TEXT,
    reason TEXT NOT NULL
);
-- B3：每一轮组合明确哪些素材进入、在哪一层；产物成为后续素材。
CREATE TABLE IF NOT EXISTS formation_rounds (
    round_id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer INTEGER NOT NULL CHECK (layer >= 0),
    purpose TEXT NOT NULL,
    basis_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED'))
);
CREATE TABLE IF NOT EXISTS round_materials (
    round_id INTEGER NOT NULL REFERENCES formation_rounds(round_id),
    material_id TEXT NOT NULL REFERENCES materials(material_id),
    reason TEXT NOT NULL,
    PRIMARY KEY (round_id, material_id)
);
-- N6：包之间的概念关系（图引用），与成员关系分开，允许成环。
CREATE TABLE IF NOT EXISTS package_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_package TEXT NOT NULL,
    from_version INTEGER NOT NULL,
    to_package TEXT NOT NULL,
    to_version INTEGER NOT NULL,
    relation TEXT NOT NULL,
    basis_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY (from_package, from_version) REFERENCES package_versions(package_id, version),
    FOREIGN KEY (to_package, to_version) REFERENCES package_versions(package_id, version)
);
CREATE TABLE IF NOT EXISTS package_relation_retractions (
    relation_id INTEGER PRIMARY KEY REFERENCES package_relations(relation_id),
    basis_json TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS package_versions (
    package_id TEXT NOT NULL REFERENCES packages(package_id),
    version INTEGER NOT NULL,
    parent_version INTEGER,
    change TEXT NOT NULL,
    reason TEXT NOT NULL,
    basis_json TEXT NOT NULL,
    computation_json TEXT NOT NULL,
    regression_json TEXT,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (package_id, version)
);
CREATE TABLE IF NOT EXISTS version_members (
    package_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    position INTEGER NOT NULL,
    material_id TEXT NOT NULL REFERENCES materials(material_id),
    difference_json TEXT NOT NULL,
    context_json TEXT,
    value_json TEXT NOT NULL,      -- B4：成员的值；没给出时记 unknown
    sources_json TEXT NOT NULL,    -- 这个成员自己的来源经验（图谱 0.6：成员、来源、条件和差异）
    PRIMARY KEY (package_id, version, position),
    FOREIGN KEY (package_id, version) REFERENCES package_versions(package_id, version)
);
CREATE INDEX IF NOT EXISTS idx_members_material ON version_members(material_id);

-- 记忆边界阀（valve.py）：世界、前提、工作缓存。
CREATE TABLE IF NOT EXISTS worlds (
    world_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    basis_json TEXT NOT NULL
);
INSERT OR IGNORE INTO worlds(world_id, name, description, basis_json) VALUES (
    'physical', '物理世界',
    '没有说明时的默认物理世界；默认归属不代表事实已经证实', '[]');
CREATE TABLE IF NOT EXISTS world_tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('experience', 'memory', 'package')),
    target_ref TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds(world_id),
    action TEXT NOT NULL CHECK (action IN ('ADD', 'REMOVE')),
    basis_json TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS premises (
    premise_id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id TEXT NOT NULL REFERENCES worlds(world_id),
    content_hash TEXT NOT NULL REFERENCES contents(content_hash),
    scope_json TEXT NOT NULL,
    proposed_by TEXT NOT NULL CHECK (proposed_by IN ('DECLARED', 'SYSTEM')),
    basis_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS premise_events (
    premise_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    premise_id INTEGER NOT NULL REFERENCES premises(premise_id),
    action TEXT NOT NULL CHECK (action IN ('CONFIRM', 'REVOKE')),
    basis_json TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_caches (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED'))
);
CREATE TABLE IF NOT EXISTS cache_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_id INTEGER NOT NULL REFERENCES work_caches(cache_id),
    action TEXT NOT NULL CHECK (action IN ('ENTER', 'EXIT')),
    item_kind TEXT NOT NULL CHECK (item_kind IN ('world', 'package', 'memory', 'experience')),
    item_ref TEXT NOT NULL,
    priority INTEGER,
    cross_world INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL
);

-- 事件链＝广义 AST（event_ast.py）：结构层。
CREATE TABLE IF NOT EXISTS ast_nodes (
    node_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    condition_text TEXT,
    basis_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (node_id, version)
);
CREATE TABLE IF NOT EXISTS ast_slots (
    node_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    slot TEXT NOT NULL,
    constraint_json TEXT NOT NULL,
    PRIMARY KEY (node_id, version, slot),
    FOREIGN KEY (node_id, version) REFERENCES ast_nodes(node_id, version)
);
CREATE TABLE IF NOT EXISTS ast_children (
    node_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    ord INTEGER NOT NULL,
    child_id TEXT NOT NULL,
    child_version INTEGER NOT NULL,
    slot_map_json TEXT NOT NULL,
    PRIMARY KEY (node_id, version, ord),
    FOREIGN KEY (node_id, version) REFERENCES ast_nodes(node_id, version),
    FOREIGN KEY (child_id, child_version) REFERENCES ast_nodes(node_id, version)
);

-- 事件链＝广义 AST：发生层。
CREATE TABLE IF NOT EXISTS occurrences (
    occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    parent_occurrence_id INTEGER REFERENCES occurrences(occurrence_id),
    child_ord INTEGER,
    cache_id INTEGER NOT NULL REFERENCES work_caches(cache_id),
    experience_id INTEGER REFERENCES experiences(experience_id),
    memory_id INTEGER REFERENCES memory_items(memory_id),
    CHECK ((experience_id IS NULL) != (memory_id IS NULL)),
    FOREIGN KEY (node_id, version) REFERENCES ast_nodes(node_id, version)
);
CREATE TABLE IF NOT EXISTS occurrence_bindings (
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(occurrence_id),
    slot TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('BOUND', 'CANDIDATES', 'GAP')),
    value_json TEXT NOT NULL,
    inherited INTEGER NOT NULL,
    PRIMARY KEY (occurrence_id, slot)
);
CREATE TABLE IF NOT EXISTS condition_checks (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(occurrence_id),
    state TEXT NOT NULL CHECK (state IN ('SATISFIED', 'UNSATISFIED', 'UNKNOWN')),
    evidence_json TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS flow_steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(occurrence_id),
    from_face TEXT NOT NULL CHECK (from_face IN ('what', 'why', 'how')),
    to_face TEXT NOT NULL CHECK (to_face IN ('what', 'why', 'how')),
    inputs_json TEXT NOT NULL,
    outputs_json TEXT NOT NULL,
    note TEXT NOT NULL
);

-- 计算经历（calls.py）：一次包内计算调用。是溯源依据，不是记忆。
CREATE TABLE IF NOT EXISTS calls (
    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL UNIQUE REFERENCES experiences(experience_id),
    cache_id INTEGER NOT NULL REFERENCES work_caches(cache_id),
    cache_log_mark INTEGER NOT NULL,   -- v0.15：调用当时缓存记录到哪一条，用来重建当时的可见视图
    occurrence_id INTEGER REFERENCES occurrences(occurrence_id),
    package_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    computation_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    context_json TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    no_answer_json TEXT,
    FOREIGN KEY (package_id, version) REFERENCES package_versions(package_id, version)
);
-- 世界或前提改变后需要重查的调用（只标记，不自动重算）。
CREATE TABLE IF NOT EXISTS rechecks (
    recheck_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL REFERENCES calls(call_id),
    trigger_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'DONE')),
    resolution TEXT
);
CREATE TABLE IF NOT EXISTS call_candidates (
    call_id INTEGER NOT NULL REFERENCES calls(call_id),
    row INTEGER NOT NULL,
    position INTEGER NOT NULL,
    material_id TEXT NOT NULL REFERENCES materials(material_id),
    difference_json TEXT NOT NULL,
    evaluation_json TEXT NOT NULL,
    decision TEXT NOT NULL,
    PRIMARY KEY (call_id, row)
);

-- 修正记录（corrections.py）：目标、依据与修订内容。
CREATE TABLE IF NOT EXISTS corrections (
    correction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    target_json TEXT NOT NULL,
    basis_json TEXT NOT NULL,
    revision_json TEXT NOT NULL,
    reason TEXT NOT NULL
);
"""
