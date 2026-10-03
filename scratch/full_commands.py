import os
import re

cogs_dir = "cogs"
output = []

for f in sorted(os.listdir(cogs_dir)):
    if f.endswith(".py") and not f.startswith("__"):
        path = os.path.join(cogs_dir, f)
        with open(path, "r", encoding="utf-8", errors="ignore") as fp:
            content = fp.read()

        groups = re.findall(r'(\w+)\s*=\s*app_commands\.Group\s*\(\s*name=["\']([^"\']+)["\']', content)
        group_map = {var: name for var, name in groups}
        
        # standalone app commands
        top_cmds = re.findall(r'@app_commands\.command\s*\(\s*name=["\']([^"\']+)["\']', content)
        
        # group subcommands
        sub_cmds = re.findall(r'@(\w+)\.command\s*\(\s*name=["\']([^"\']+)["\']', content)
        
        # prefix commands
        pre_cmds = re.findall(r'@commands\.command\s*\(\s*name=["\']([^"\']+)["\']', content)

        cmds_str = []
        for cmd in top_cmds:
            cmds_str.append(f"/{cmd}")
        for grp_var, cmd in sub_cmds:
            grp_name = group_map.get(grp_var, grp_var)
            cmds_str.append(f"/{grp_name} {cmd}")
        for cmd in pre_cmds:
            cmds_str.append(f"!{cmd}")

        output.append((f, len(content.splitlines()), cmds_str))

for filename, lines, cmds in output:
    print(f"### `{filename}` ({lines} lines, {len(cmds)} commands)")
    if cmds:
        print(", ".join(cmds))
    else:
        print("*(Event-only or helper cog)*")
    print()
