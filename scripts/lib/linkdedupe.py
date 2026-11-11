"""Plugin-aware planning for the context optimizer (Python stdlib only).

Two plans, both opt-in:

  plan_dedupe         a skill that sits in .claude/skills/ as a symlink and is
                      also shipped by an enabled plugin loads twice. The link
                      goes; the plugin copy and the link's target stay.
  plan_plugin_skills  compact the descriptions of plugin skills in place. A
                      plugin update replaces the edited files, so this lasts
                      until the next update.

`skillOverrides` cannot be used for plugin skills: Claude Code applies it to
personal and project skills only. It is used here for one case, a personal
copy that is byte-identical to the plugin's.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import context_cost  # noqa: E402
import optimize  # noqa: E402


def plan_dedupe(root):
    plan = optimize.new_plan()
    shipped = {item["name"]: item for item in context_cost.plugin_skills(root)}
    muted = {}
    for path in context_cost.skill_files(root):
        name = context_cost.skill_name(path)
        twin = shipped.get(name)
        if not twin:
            continue
        folder = path.parent
        relative = folder.relative_to(root).as_posix()
        if folder.is_symlink():
            plan["remove_links"][relative] = f"{twin['plugin']} plugin"
            plan["notes"].append(f"dedupe: {relative} is also loaded by the {twin['plugin']} plugin; "
                                 f"link removed, {folder.resolve()} kept")
        elif context_cost.read_text(path) == context_cost.read_text(twin["path"]):
            muted[name] = "off"
            plan["notes"].append(f"dedupe: {relative} is identical to the {twin['plugin']} plugin's copy; "
                                 f"skillOverrides off")
        else:
            plan["warnings"].append(f"dedupe: {relative} shares its name with a {twin['plugin']} plugin skill "
                                    f"but differs from it; kept both")
    if muted:
        plan["settings"]["skillOverrides"] = muted
    if not plan["remove_links"] and not muted:
        plan["notes"].append("dedupe: no skill is loaded twice")
    return plan


def plan_plugin_skills(root, limit=optimize.DESCRIPTION_LIMIT, select=None):
    """Compact plugin skill descriptions. `select(item)` narrows which skills are touched."""
    plans, outside = [], 0
    for item in context_cost.plugin_skills(root):
        if select and not select(item):
            continue
        path = item["path"]
        if root.resolve() not in path.resolve().parents:
            outside += 1
            continue
        inside = root / path.resolve().relative_to(root.resolve())
        plans.append(optimize._plan_one_skill(root, inside, False, limit, split=False))
    plan = optimize.merge_plans(*plans)
    plan["notes"] = [note.replace("skills:", "plugins:", 1) for note in plan["notes"]]
    if outside:
        plan["warnings"].append(f"plugins: {outside} plugin skill(s) live outside {root}; left unchanged")
    if plan["writes"]:
        plan["warnings"].append("plugins: a plugin update replaces these files; run the optimizer again after one")
    return plan
