"""知识包登记（名词解释 v0.14 第二、三节与 v0.8“包内计算、参考系与局部修正”）。

要点：
- 知识包与索引包是同一对象。第一个成员确立本包参考系，存续期间不能更换，也不自动换锚。
- 版本只追加、不原地修改：成员变化、存异结果更新或计算更新都生成新版本，旧版本保留可回查。
- 每个版本登记本包的计算：输入及含义、候选对应、输出解释（尺子与方向）、训练依据、适用层级、参数版本。
- 存异：差异的具体公式尚未确定，这里保存带 `kind` 与 `scale`（哪把尺子）的记录；未提供时记为 unknown，不记为 0。
  v0.14：“偏差必须在存异结果中登记，并随成员引用交给后续计算”——学到的偏移用 record_differences 写回。
- 素材 ID 只用于寻址，不当作有序的语义数值。
- R2（包内评价修正）：依据必须是外部反馈，而且是对本包当前版本某次调用（calls.py）的反馈；要写明回归检查结果。
- R3（参考系变更）：把原包裁剪，并要求先处理所有引用它的上层包。
- R2、R3 都另写一条修正记录（corrections.py）。

2026-10-28 补充（对照报告 B2、B3、B4、N6；名词解释 v0.14 与图谱 0.6／v0.17）：
- B4 成员：除差异与上下文外，还保留成员的“值”（没给出就记 unknown）和这个成员自己的来源经验。
- B3 轮次：每一轮组合先写明层级和进入本轮的素材（“迭代本身就是边界”）；本轮登记的包只能用本轮素材，
  计算登记的层级必须与本轮一致；产物（包）成为后续轮次的素材。
- B2 局部／全局、候选／可发布（工作解释）：在某个工作缓存里登记的包是工作侧局部包，只在那个缓存里可用；
  推广到全局要写依据和回归检查（局部成功不直接推广成全局规律）。登记不等于发布：发布要观察或实际执行的证据，
  而且只能发布全局包。不在任何工作缓存里登记的包，按学习侧产物处理，直接是全局的。
- N6 概念关系：包与包之间可以用图引用（允许成环），与成员关系分开；只追加，撤回另记。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .corrections import CorrectionKind, insert_correction
from .experience import EVIDENCE_SOURCES, ExperienceLog
from .relation_eval import EvaluationSpec
from .store import Store, content_hash, now_iso

SELF_REFERENCE = {"kind": "self_reference"}  # 自指零偏差：零不是未知，也不是缺失
UNKNOWN = {"kind": "unknown"}
_SPECIAL_DIFFERENCES = ("self_reference", "unknown")

REQUIRED_COMPUTATION_KEYS = (
    "computation_id",      # 计算身份
    "inputs",              # 所需输入及其含义
    "candidate_mapping",   # 候选对应
    "output_meaning",      # 输出解释（文字）
    "output_evaluation",   # 输出解释（尺子与方向，见 relation_eval）
    "training_basis",      # 训练依据
    "layer",               # 适用层级：非负整数，未知写 UNKNOWN
    "parameter_version",   # 参数版本引用：{"kind": ...}；kind 为 weights 时必须有 sha256
)
REGRESSION_STATUSES = ("passed", "failed", "not_run")


class DependencyError(RuntimeError):
    def __init__(self, package_id: str, unhandled: list[str]):
        super().__init__(f"裁剪 {package_id} 前必须处理引用它的上层包：{unhandled}")
        self.package_id = package_id
        self.unhandled = unhandled


@dataclass(frozen=True)
class MemberSpec:
    material_id: str
    difference: Optional[dict] = None
    context: Optional[dict] = None   # 上下文与条件
    value: Any = None                # B4：成员的值；None 表示没给出，登记为 unknown
    sources: tuple = ()              # 这个成员自己的来源经验编号


@dataclass(frozen=True)
class Member:
    position: int
    material_id: str
    difference: dict
    context: Optional[dict]
    value: Any = None
    sources: tuple = ()


@dataclass(frozen=True)
class PackageVersion:
    package_id: str
    version: int
    parent_version: Optional[int]
    change: str
    reason: str
    basis_event_ids: list[int]
    computation: dict
    members: list[Member]
    regression: Optional[dict] = None

    @property
    def reference(self) -> str:
        return self.members[0].material_id

    @property
    def frame(self) -> str:
        """本版本的参考框架名，用于关系评价（relation_eval.Evaluation.frame）。"""
        return frame_name(self.package_id, self.version)


def frame_name(package_id: str, version: int) -> str:
    return f"pkg:{package_id}@v{version}"


class PackageRegistry:
    def __init__(self, store: Store, experiences: ExperienceLog):
        self.store = store
        self.experiences = experiences

    # ---------- 素材 ----------

    def add_raw(self, content: str) -> str:
        return self._add_content_material("raw", content)

    def add_method(self, content: str) -> str:
        """已对象化的方法或规则，也可以作为素材。"""
        return self._add_content_material("method", content)

    def _add_content_material(self, kind: str, content: str) -> str:
        material_id = f"{kind}:{content_hash(content)}"
        with self.store.transaction() as c:
            h = self.store.put_content(content)
            c.execute(
                "INSERT OR IGNORE INTO materials(material_id, kind, content_hash) VALUES (?, ?, ?)",
                (material_id, kind, h),
            )
        return material_id

    @staticmethod
    def package_material(package_id: str) -> str:
        return f"pkg:{package_id}"

    def material_exists(self, material_id: str) -> bool:
        return self.store.conn.execute(
            "SELECT 1 FROM materials WHERE material_id = ?", (material_id,)
        ).fetchone() is not None

    # ---------- 登记与版本 ----------

    def register_package(
        self,
        package_id: str,
        name: str,
        members: Sequence[MemberSpec],
        computation: dict,
        basis_event_ids: Sequence[int],
        reason: str,
        reorganized_from: Sequence[str] = (),
        round_id: Optional[int] = None,
        work_cache_id: Optional[int] = None,
    ) -> PackageVersion:
        """登记新包（版本 1）。第一个成员确立参考系。

        round_id：在哪一轮组合中形成（B3）；给出时，成员必须是本轮素材，计算层级必须等于本轮层级。
        work_cache_id：在哪个工作缓存里登记（B2）；给出时是工作侧局部包，只在这个缓存里可用。
        """
        if not members:
            raise ValueError("知识包至少要有一个成员")
        if self.store.conn.execute("SELECT 1 FROM packages WHERE package_id = ?", (package_id,)).fetchone():
            raise ValueError(f"包 {package_id} 已存在；参考或语义变化必须使用新身份")
        check_computation(computation)
        self._check_training_link(computation)
        self._check_events_exist(basis_event_ids)
        for old in reorganized_from:
            if self._status(old) != "CROPPED":
                raise ValueError(f"重组来源 {old} 必须先被裁剪")
        if round_id is not None:
            rnd = self.round_info(round_id)
            if rnd["status"] != "OPEN":
                raise ValueError(f"第 {round_id} 轮已结束，不能再在其中登记包")
            outside = [m.material_id for m in members if m.material_id not in rnd["materials"]]
            if outside:
                raise ValueError(f"这些素材没有进入第 {round_id} 轮：{outside}（每轮先写明哪些素材进入组合）")
            if computation["layer"] != rnd["layer"]:
                raise ValueError(f"计算登记的层级 {computation['layer']} 与本轮层级 {rnd['layer']} 不一致")
        if work_cache_id is not None:
            row = self.store.conn.execute("SELECT status FROM work_caches WHERE cache_id = ?", (work_cache_id,)).fetchone()
            if row is None or row[0] != "OPEN":
                raise ValueError(f"工作缓存 {work_cache_id} 不存在或已关闭")
        rows = self._member_rows(package_id, members)
        with self.store.transaction() as c:
            c.execute(
                "INSERT INTO materials(material_id, kind, package_id) VALUES (?, 'package', ?)",
                (self.package_material(package_id), package_id),
            )
            c.execute(
                "INSERT INTO packages(package_id, name, reference_material_id, origin_json, round_id, home_cache_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (package_id, name, members[0].material_id,
                 json.dumps({"reorganized_from": list(reorganized_from)}, ensure_ascii=False), round_id, work_cache_id),
            )
            self._insert_version(c, package_id, 1, None, "formation", reason, basis_event_ids, computation, rows)
        return self.latest(package_id)

    def add_members(
        self, package_id: str, new_members: Sequence[MemberSpec], basis_event_ids: Sequence[int], reason: str
    ) -> PackageVersion:
        """追加成员，生成新版本；参考系与已有成员不变。"""
        cur = self._require_active(package_id)
        self._check_events_exist(basis_event_ids)
        start = len(cur.members)
        specs = [_spec(m) for m in cur.members] + list(new_members)
        rows = self._member_rows(package_id, specs)
        assert all(rows[i] == _member_row(cur.members[i]) for i in range(start))
        with self.store.transaction() as c:
            self._insert_version(
                c, package_id, cur.version + 1, cur.version, "members_added", reason,
                basis_event_ids, cur.computation, rows,
            )
        return self.latest(package_id)

    def record_differences(
        self, package_id: str, differences: dict[int, dict], basis_event_ids: Sequence[int], reason: str
    ) -> PackageVersion:
        """登记存异结果：把非参考成员相对本包参考的差异写回知识库，生成新版本。成员与参考不变。

        依据通常是产生这些差异的计算经历（calls.py）或训练记录；必须存在，可以是系统自己的计算。
        """
        cur = self._require_active(package_id)
        differences = {int(k): v for k, v in differences.items()}
        if not differences:
            raise ValueError("没有要登记的差异")
        if not basis_event_ids:
            raise ValueError("存异结果必须写明依据（哪次计算或训练产生了它）")
        self._check_events_exist(basis_event_ids)
        for pos in differences:
            if not 0 <= int(pos) < len(cur.members):
                raise ValueError(f"成员位置 {pos} 不存在")
            if int(pos) == 0:
                raise ValueError("第一个成员是参考系，差异固定为自指零偏差，不能改写")
        specs = [MemberSpec(m.material_id, differences.get(m.position, m.difference), m.context, m.value, m.sources)
                 for m in cur.members]
        rows = self._member_rows(package_id, specs)
        with self.store.transaction() as c:
            self._insert_version(
                c, package_id, cur.version + 1, cur.version, "differences_recorded", reason,
                basis_event_ids, cur.computation, rows,
            )
        return self.latest(package_id)

    def update_computation(
        self, package_id: str, computation: dict, feedback_ids: Sequence[int], reason: str, regression: dict
    ) -> PackageVersion:
        """R2：参考与成员不动，只更新包内计算，生成新的计算版本。

        - 依据必须是外部反馈（不能是模型自己的推导、计算经历或回忆），且没有被核实为相反。
        - 每条反馈都必须是对本包“当前版本”某次调用的反馈；对应旧版本的反馈不直接更新。
        - 必须写明无关组合的回归检查：passed／not_run 可以登记（not_run 如实保留），failed 拒绝。
        """
        cur = self._require_active(package_id)
        check_computation(computation)
        self._check_training_link(computation)
        self.experiences.require_external_feedback(feedback_ids, "R2 包内评价修正")
        for fb in feedback_ids:
            calls = self._calls_answered_by(fb)
            if not calls:
                raise ValueError(f"反馈 {fb} 没有对应任何一次调用，不能作为 R2 的依据")
            if (package_id, cur.version) not in calls:
                raise ValueError(f"反馈 {fb} 对应的不是包 {package_id} 的当前版本 v{cur.version}，不直接更新")
        _check_regression(regression)
        if regression["status"] == "failed":
            raise ValueError("无关组合回归检查未通过，不登记新计算版本")
        rows = [_member_row(m) for m in cur.members]
        with self.store.transaction() as c:
            self._insert_version(
                c, package_id, cur.version + 1, cur.version, "computation_updated", reason,
                feedback_ids, computation, rows, regression,
            )
            insert_correction(c, CorrectionKind.R2_PACKAGE_EVALUATION,
                              {"package_id": package_id, "from_version": cur.version, "to_version": cur.version + 1},
                              feedback_ids, {"computation_id": computation["computation_id"],
                                             "parameter_version": computation["parameter_version"]}, reason)
        return self.latest(package_id)

    # ---------- R3：裁剪与依赖 ----------

    def dependents(self, package_id: str) -> list[str]:
        """最新版本中把本包当作成员的活动包。"""
        rows = self.store.conn.execute(
            """
            SELECT DISTINCT vm.package_id FROM version_members vm
            JOIN packages p ON p.package_id = vm.package_id AND p.status = 'ACTIVE'
            WHERE vm.material_id = ?
              AND vm.version = (SELECT MAX(version) FROM package_versions v WHERE v.package_id = vm.package_id)
            ORDER BY vm.package_id
            """,
            (self.package_material(package_id),),
        ).fetchall()
        return [r[0] for r in rows]

    def crop(self, package_id: str, reason: str, dependent_plan: dict[str, str], basis_event_ids: Sequence[int]) -> None:
        """R3：参照含义必须改变时裁剪原包（不删除）。

        每个引用它的上层包都要在 dependent_plan 中给出处理说明；依据可以是复核记录，必须存在。
        """
        cur = self._require_active(package_id)
        if not basis_event_ids:
            raise ValueError("R3 裁剪必须写明依据")
        self._check_events_exist(basis_event_ids)
        unhandled = [d for d in self.dependents(package_id) if d not in dependent_plan]
        if unhandled:
            raise DependencyError(package_id, unhandled)
        with self.store.transaction() as c:
            c.execute(
                "UPDATE packages SET status = 'CROPPED', crop_json = ? WHERE package_id = ?",
                (json.dumps({"reason": reason, "dependent_plan": dependent_plan,
                             "basis": list(basis_event_ids)}, ensure_ascii=False), package_id),
            )
            insert_correction(c, CorrectionKind.R3_REFERENCE_STRUCTURE,
                              {"package_id": package_id, "version": cur.version}, basis_event_ids,
                              {"status": "CROPPED", "dependent_plan": dependent_plan}, reason)

    def dangling_references(self) -> list[tuple[str, str]]:
        """仍在最新版本中引用已裁剪包的活动包：(上层包, 被裁剪包)。逐层检查依赖时使用。"""
        rows = self.store.conn.execute(
            """
            SELECT DISTINCT vm.package_id, m.package_id FROM version_members vm
            JOIN materials m ON m.material_id = vm.material_id AND m.kind = 'package'
            JOIN packages child ON child.package_id = m.package_id AND child.status = 'CROPPED'
            JOIN packages parent ON parent.package_id = vm.package_id AND parent.status = 'ACTIVE'
            WHERE vm.version = (SELECT MAX(version) FROM package_versions v WHERE v.package_id = vm.package_id)
            ORDER BY vm.package_id, m.package_id
            """
        ).fetchall()
        return [(a, b) for a, b in rows]

    # ---------- B3：组合轮次（迭代本身就是边界） ----------

    def open_round(self, layer: int, materials: Sequence[str], purpose: str, basis_ids: Sequence[int]) -> int:
        """开始一轮组合：写明层级与进入本轮的素材。"""
        if not (isinstance(layer, int) and not isinstance(layer, bool) and layer >= 0):
            raise ValueError("层级必须是非负整数")
        if not materials:
            raise ValueError("每一轮都要写明哪些素材进入组合")
        if not basis_ids:
            raise ValueError("开始一轮组合要写明依据")
        self._check_events_exist(basis_ids)
        with self.store.transaction() as c:
            round_id = c.execute("INSERT INTO formation_rounds(layer, purpose, basis_json) VALUES (?, ?, ?)",
                                 (layer, purpose, json.dumps(list(basis_ids)))).lastrowid
            self._add_round_materials(c, round_id, materials, "开始本轮")
        return round_id

    def extend_round(self, round_id: int, materials: Sequence[str], reason: str) -> None:
        """本轮进行中追加素材（记录原因，不改写已有素材）。"""
        if self.round_info(round_id)["status"] != "OPEN":
            raise ValueError(f"第 {round_id} 轮已结束")
        with self.store.transaction() as c:
            self._add_round_materials(c, round_id, materials, reason)

    def close_round(self, round_id: int) -> list[str]:
        """结束本轮，返回本轮的产物（包），它们可以作为后续轮次的素材。"""
        if self.round_info(round_id)["status"] != "OPEN":
            raise ValueError(f"第 {round_id} 轮已结束")
        with self.store.transaction() as c:
            c.execute("UPDATE formation_rounds SET status = 'CLOSED' WHERE round_id = ?", (round_id,))
        return self.round_info(round_id)["products"]

    def round_info(self, round_id: int) -> dict:
        c = self.store.conn
        row = c.execute("SELECT layer, purpose, status FROM formation_rounds WHERE round_id = ?", (round_id,)).fetchone()
        if row is None:
            raise KeyError(round_id)
        layer, purpose, status = row
        materials = [r[0] for r in c.execute(
            "SELECT material_id FROM round_materials WHERE round_id = ? ORDER BY material_id", (round_id,))]
        products = [r[0] for r in c.execute(
            "SELECT package_id FROM packages WHERE round_id = ? ORDER BY package_id", (round_id,))]
        return {"round_id": round_id, "layer": layer, "purpose": purpose, "status": status,
                "materials": materials, "products": products}

    def _add_round_materials(self, c, round_id: int, materials: Sequence[str], reason: str) -> None:
        for mat in materials:
            if not self.material_exists(mat):
                raise ValueError(f"素材 {mat} 未登记")
            if mat.startswith("pkg:") and self._status(mat[len("pkg:"):]) != "ACTIVE":
                raise ValueError(f"素材 {mat} 对应的包已裁剪，不能再进入组合")
        c.executemany("INSERT OR IGNORE INTO round_materials(round_id, material_id, reason) VALUES (?, ?, ?)",
                      [(round_id, m, reason) for m in materials])

    # ---------- B2：局部／全局，候选／可发布 ----------

    def standing(self, package_id: str) -> tuple[str, Optional[int]]:
        """（"LOCAL", 所属工作缓存）或（"GLOBAL", None）。"""
        row = self.store.conn.execute("SELECT home_cache_id FROM packages WHERE package_id = ?", (package_id,)).fetchone()
        if row is None:
            raise KeyError(package_id)
        if row[0] is None or self._has_event(package_id, "PROMOTE"):
            return ("GLOBAL", None)
        return ("LOCAL", row[0])

    def publication(self, package_id: str) -> str:
        """登记不等于发布：没有发布记录的包都是候选（CANDIDATE）。"""
        self._status(package_id)
        return "PUBLISHED" if self._has_event(package_id, "PUBLISH") else "CANDIDATE"

    def promote(self, package_id: str, basis_ids: Sequence[int], reason: str, regression: dict) -> None:
        """工作侧局部包推广到全局。局部成功不直接推广：要写依据，并写明更广范围的回归检查。"""
        self._require_active(package_id)
        if self.standing(package_id)[0] == "GLOBAL":
            raise ValueError(f"包 {package_id} 已经是全局的")
        if not basis_ids:
            raise ValueError("推广到全局要写明依据")
        self._check_events_exist(basis_ids)
        _check_regression(regression)
        if regression["status"] == "failed":
            raise ValueError("更广范围的回归检查未通过，不推广")
        with self.store.transaction() as c:
            c.execute("INSERT INTO package_events(package_id, action, basis_json, regression_json, reason)"
                      " VALUES (?, 'PROMOTE', ?, ?, ?)", (package_id, json.dumps(list(basis_ids)), _dumps(regression), reason))

    def publish(self, package_id: str, evidence_ids: Sequence[int], reason: str) -> None:
        """发布为可发布知识：只能发布全局包，依据必须是观察或实际执行的证据。"""
        self._require_active(package_id)
        if self.standing(package_id)[0] != "GLOBAL":
            raise ValueError("工作侧局部包要先推广到全局，才能发布")
        if self.publication(package_id) == "PUBLISHED":
            raise ValueError(f"包 {package_id} 已发布")
        if not evidence_ids:
            raise ValueError("发布必须给出证据")
        for ev in evidence_ids:
            if not self.experiences.exists(ev):
                raise ValueError(f"证据 {ev} 不存在")
            src = self.experiences.get(ev).source_type
            if src not in EVIDENCE_SOURCES:
                raise ValueError(f"记录 {ev} 的来源是 {src.value}，不能作为发布的证据")
        with self.store.transaction() as c:
            c.execute("INSERT INTO package_events(package_id, action, basis_json, reason) VALUES (?, 'PUBLISH', ?, ?)",
                      (package_id, json.dumps(list(evidence_ids)), reason))

    def _has_event(self, package_id: str, action: str) -> bool:
        return self.store.conn.execute("SELECT 1 FROM package_events WHERE package_id = ? AND action = ?",
                                       (package_id, action)).fetchone() is not None

    # ---------- N6：包之间的概念关系（图引用） ----------

    def relate(self, from_package: str, from_version: int, to_package: str, to_version: int, relation: str,
               basis_ids: Sequence[int], reason: str) -> int:
        """登记两个包版本之间的概念关系。与成员关系分开，允许成环；不改变任何包的成员或参考。"""
        for pid, ver in ((from_package, from_version), (to_package, to_version)):
            try:
                self.version(pid, ver)
            except KeyError:
                raise ValueError(f"知识包版本 {pid}@{ver} 不存在") from None
        if not relation:
            raise ValueError("要写明是什么关系")
        if not basis_ids:
            raise ValueError("登记概念关系要写明依据")
        self._check_events_exist(basis_ids)
        with self.store.transaction() as c:
            return c.execute(
                "INSERT INTO package_relations(from_package, from_version, to_package, to_version, relation, basis_json,"
                " reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (from_package, from_version, to_package, to_version, relation, json.dumps(list(basis_ids)), reason)).lastrowid

    def retract_relation(self, relation_id: int, basis_ids: Sequence[int], reason: str) -> None:
        """撤回一条概念关系：原记录保留，另记撤回。"""
        if self.store.conn.execute("SELECT 1 FROM package_relations WHERE relation_id = ?", (relation_id,)).fetchone() is None:
            raise ValueError(f"关系 {relation_id} 不存在")
        if self.store.conn.execute("SELECT 1 FROM package_relation_retractions WHERE relation_id = ?",
                                   (relation_id,)).fetchone() is not None:
            raise ValueError(f"关系 {relation_id} 已撤回")
        if not basis_ids:
            raise ValueError("撤回要写明依据")
        self._check_events_exist(basis_ids)
        with self.store.transaction() as c:
            c.execute("INSERT INTO package_relation_retractions(relation_id, basis_json, reason) VALUES (?, ?, ?)",
                      (relation_id, json.dumps(list(basis_ids)), reason))

    def relations(self, package_id: str, include_retracted: bool = False) -> list[dict]:
        """与这个包（任何版本）有关的概念关系，两个方向都列出。"""
        rows = self.store.conn.execute(
            "SELECT r.relation_id, r.from_package, r.from_version, r.to_package, r.to_version, r.relation,"
            " x.relation_id IS NOT NULL FROM package_relations r"
            " LEFT JOIN package_relation_retractions x ON x.relation_id = r.relation_id"
            " WHERE r.from_package = ? OR r.to_package = ? ORDER BY r.relation_id", (package_id, package_id)).fetchall()
        return [{"relation_id": rid, "from": (fp, fv), "to": (tp, tv), "relation": rel, "retracted": bool(ret)}
                for rid, fp, fv, tp, tv, rel, ret in rows if include_retracted or not ret]

    # ---------- 读取 ----------

    def latest(self, package_id: str) -> PackageVersion:
        row = self.store.conn.execute(
            "SELECT MAX(version) FROM package_versions WHERE package_id = ?", (package_id,)
        ).fetchone()
        if row is None or row[0] is None:
            raise KeyError(package_id)
        return self.version(package_id, row[0])

    def version(self, package_id: str, version: int) -> PackageVersion:
        row = self.store.conn.execute(
            "SELECT parent_version, change, reason, basis_json, computation_json, regression_json FROM package_versions"
            " WHERE package_id = ? AND version = ?",
            (package_id, version),
        ).fetchone()
        if row is None:
            raise KeyError((package_id, version))
        parent, change, reason, basis, comp, regression = row
        members = [
            Member(pos, mat, json.loads(diff), None if ctx is None else json.loads(ctx), json.loads(val),
                   tuple(json.loads(src)))
            for pos, mat, diff, ctx, val, src in self.store.conn.execute(
                "SELECT position, material_id, difference_json, context_json, value_json, sources_json FROM version_members"
                " WHERE package_id = ? AND version = ? ORDER BY position",
                (package_id, version),
            )
        ]
        return PackageVersion(package_id, version, parent, change, reason, json.loads(basis), json.loads(comp),
                              members, None if regression is None else json.loads(regression))

    def status(self, package_id: str) -> str:
        return self._status(package_id)

    def active_packages(self) -> list[str]:
        return [r[0] for r in self.store.conn.execute(
            "SELECT package_id FROM packages WHERE status = 'ACTIVE' ORDER BY package_id")]

    # ---------- 内部 ----------

    def _status(self, package_id: str) -> str:
        row = self.store.conn.execute("SELECT status FROM packages WHERE package_id = ?", (package_id,)).fetchone()
        if row is None:
            raise KeyError(package_id)
        return row[0]

    def _require_active(self, package_id: str) -> PackageVersion:
        if self._status(package_id) != "ACTIVE":
            raise ValueError(f"包 {package_id} 已裁剪，不能再更新")
        return self.latest(package_id)

    def _check_events_exist(self, event_ids: Sequence[int]) -> None:
        for ev in event_ids:
            if not self.experiences.exists(ev):
                raise ValueError(f"依据记录 {ev} 不存在")

    def _check_training_link(self, computation: dict) -> None:
        """参数版本写了 training_id 时，必须对得上学习材料库里的训练记录（参数版本 ← 训练记录 ← 学习材料）。"""
        pv = computation["parameter_version"]
        if "training_id" not in pv:
            return
        row = self.store.conn.execute("SELECT parameter_version_json, computation_id FROM training_runs"
                                      " WHERE training_id = ?", (pv["training_id"],)).fetchone()
        if row is None:
            raise ValueError(f"训练记录 {pv['training_id']} 不存在")
        recorded = json.loads(row[0])
        if recorded.get("sha256") != pv.get("sha256") or row[1] != computation["computation_id"]:
            raise ValueError("参数版本与训练记录不一致（权重哈希或计算身份不同）")

    def _calls_answered_by(self, experience_id: int) -> set[tuple[str, int]]:
        """这条经验作为反馈所对应的调用：{(包, 版本)}。"""
        rows = self.store.conn.execute(
            "SELECT c.package_id, c.version FROM experience_links l JOIN calls c ON c.experience_id = l.target_experience_id"
            " WHERE l.experience_id = ? AND l.relation = 'feedback_for'", (experience_id,)).fetchall()
        return {(p, v) for p, v in rows}

    def _member_rows(self, package_id: str, members: Sequence[MemberSpec]) -> list[tuple]:
        rows = []
        for pos, m in enumerate(members):
            if not self.material_exists(m.material_id):
                raise ValueError(f"素材 {m.material_id} 未登记")
            if m.material_id == self.package_material(package_id) or self._reaches(m.material_id, package_id):
                raise ValueError(f"素材 {m.material_id} 会使包 {package_id} 包含自身")
            if m.material_id.startswith("pkg:") and self._status(m.material_id[len("pkg:"):]) != "ACTIVE":
                raise ValueError(f"素材 {m.material_id} 对应的包已裁剪，不能再被组合")
            if pos == 0:
                if m.difference not in (None, SELF_REFERENCE):
                    raise ValueError("第一个成员是参考系，差异只能是自指零偏差")
                diff = SELF_REFERENCE
            elif m.difference is None:
                diff = UNKNOWN
            else:
                diff = m.difference
                _check_difference(diff)
            value = UNKNOWN if m.value is None else m.value
            sources = [int(s) for s in m.sources]
            self._check_events_exist(sources)
            rows.append((pos, m.material_id, _dumps(diff), None if m.context is None else _dumps(m.context),
                         _dumps(value), json.dumps(sources)))
        return rows

    def _reaches(self, material_id: str, target_package_id: str) -> bool:
        """material 是否（经由最新版本的成员关系）包含 target 包。"""
        seen: set[str] = set()
        stack = [material_id]
        target = self.package_material(target_package_id)
        while stack:
            mat = stack.pop()
            if mat == target:
                return True
            if mat in seen or not mat.startswith("pkg:"):
                continue
            seen.add(mat)
            pid = mat[len("pkg:"):]
            try:
                stack.extend(m.material_id for m in self.latest(pid).members)
            except KeyError:
                continue
        return False

    @staticmethod
    def _insert_version(c, package_id, version, parent, change, reason, basis, computation, rows, regression=None) -> None:
        c.execute(
            "INSERT INTO package_versions(package_id, version, parent_version, change, reason, basis_json,"
            " computation_json, regression_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (package_id, version, parent, change, reason, json.dumps(list(basis)), _dumps(computation),
             None if regression is None else _dumps(regression), now_iso()),
        )
        c.executemany(
            "INSERT INTO version_members(package_id, version, position, material_id, difference_json, context_json,"
            " value_json, sources_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(package_id, version, *row) for row in rows],
        )


def check_computation(computation: dict) -> None:
    missing = [k for k in REQUIRED_COMPUTATION_KEYS if k not in computation]
    if missing:
        raise ValueError(f"包内计算登记缺少字段：{missing}")
    for item in computation["inputs"]:
        if not {"name", "meaning"} <= set(item):
            raise ValueError("每个输入都要写明 name 和 meaning")
    names = [item["name"] for item in computation["inputs"]]
    if len(names) != len(set(names)):
        raise ValueError("输入名字不能重复")
    EvaluationSpec.from_dict(computation["output_evaluation"])
    layer = computation["layer"]
    if not (layer == UNKNOWN or (isinstance(layer, int) and not isinstance(layer, bool) and layer >= 0)):
        raise ValueError("layer 必须是非负整数；未知请写 UNKNOWN，不要写 0")
    pv = computation["parameter_version"]
    if not isinstance(pv, dict) or "kind" not in pv:
        raise ValueError("parameter_version 必须是带 kind 的记录，例如 {'kind': 'none'} 或 {'kind': 'weights', 'sha256': ...}")
    if pv["kind"] == "weights" and not pv.get("sha256"):
        raise ValueError("登记权重版本时必须写明 sha256")


def _check_difference(diff) -> None:
    if not isinstance(diff, dict) or "kind" not in diff:
        raise ValueError("差异必须是带 kind 字段的记录；未知请留空，不要写 0")
    if diff["kind"] == "self_reference":
        raise ValueError("只有第一个成员（参考）是自指零偏差")
    if diff["kind"] not in _SPECIAL_DIFFERENCES and not diff.get("scale"):
        raise ValueError("差异必须写明 scale（在哪把尺子／哪个比较维度上的差异）")


def _check_regression(regression: dict) -> None:
    if not isinstance(regression, dict) or regression.get("status") not in REGRESSION_STATUSES:
        raise ValueError(f"回归检查必须写明 status，取值 {REGRESSION_STATUSES}；没做就写 not_run")
    if not regression.get("scope"):
        raise ValueError("回归检查必须写明 scope（检查了哪些无关组合，或为什么没做）")


def _member_row(m: Member) -> tuple:
    return (m.position, m.material_id, _dumps(m.difference), None if m.context is None else _dumps(m.context),
            _dumps(m.value), json.dumps([int(s) for s in m.sources]))


def _spec(m: Member) -> MemberSpec:
    return MemberSpec(m.material_id, m.difference, m.context, m.value, m.sources)


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
