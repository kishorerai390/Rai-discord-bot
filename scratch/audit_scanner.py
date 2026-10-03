import os
import re
import ast

cogs_dir = "cogs"
cog_summary = {}

for f in sorted(os.listdir(cogs_dir)):
    if f.endswith(".py") and not f.startswith("__"):
        path = os.path.join(cogs_dir, f)
        with open(path, "r", encoding="utf-8", errors="ignore") as fp:
            content = fp.read()
        
        # Regex search for commands
        app_cmds = re.findall(r'@app_commands\.command\s*\(\s*name=["\']([^"\']+)["\']', content)
        hybrid_cmds = re.findall(r'@commands\.hybrid_command\s*\(\s*name=["\']([^"\']+)["\']', content)
        prefix_cmds = re.findall(r'@commands\.command\s*\(\s*name=["\']([^"\']+)["\']', content)
        groups = re.findall(r'app_commands\.Group\s*\(\s*name=["\']([^"\']+)["\']', content)
        sub_cmds = re.findall(r'@([a-zA-Z0-9_]+)\.command\s*\(\s*name=["\']([^"\']+)["\']', content)
        tasks = re.findall(r'@tasks\.loop\s*\(', content)
        listeners = re.findall(r'@commands\.Cog\.listener\s*\(', content)

        cog_summary[f] = {
            "app_cmds": app_cmds,
            "hybrid_cmds": hybrid_cmds,
            "prefix_cmds": prefix_cmds,
            "groups": groups,
            "sub_cmds": sub_cmds,
            "task_count": len(tasks),
            "listener_count": len(listeners),
            "lines": len(content.splitlines()),
        }

print("=== COG AUDIT BREAKDOWN ===")
total_all = 0
for cog, data in cog_summary.items():
    cmd_count = len(data["app_cmds"]) + len(data["hybrid_cmds"]) + len(data["prefix_cmds"]) + len(data["sub_cmds"])
    total_all += cmd_count
    print(f"{cog:<25} | Lines: {data['lines']:<5} | Cmds: {cmd_count:<3} (App: {len(data['app_cmds'])}, Sub: {len(data['sub_cmds'])}, Hyb: {len(data['hybrid_cmds'])}, Pre: {len(data['prefix_cmds'])}) | Groups: {data['groups']} | Tasks: {data['task_count']} | Listeners: {data['listener_count']}")

print(f"\nTotal Top-Level and Sub-Commands: {total_all}")
