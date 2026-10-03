import glob
import re

md_files = glob.glob("*.md")
for fname in md_files:
    with open(fname, "r", encoding="utf-8") as f:
        lines = f.readlines()
    issues = []
    top_headers = 0
    in_code_block = False
    
    for idx, line in enumerate(lines):
        line_num = idx + 1
        raw = line.rstrip("\r\n")
        
        # MD009: Trailing spaces
        if line.endswith(" \n") or line.endswith(" \r\n") or line.endswith("\t\n"):
            issues.append(f"Line {line_num}: MD009 Trailing spaces")
            
        if raw.startswith("```"):
            if not in_code_block:
                in_code_block = True
                # MD031: Blank line before opening code fence
                if idx > 0 and lines[idx - 1].strip() != "" and not lines[idx - 1].strip().startswith("---"):
                    issues.append(f"Line {line_num}: MD031 Missing blank line before code block")
                # MD040: Code block language
                lang = raw[3:].strip()
                if not lang:
                    issues.append(f"Line {line_num}: MD040 Missing language on fenced code block")
            else:
                in_code_block = False
                # MD031: Blank line after closing code fence
                if idx < len(lines) - 1 and lines[idx + 1].strip() != "" and not lines[idx + 1].strip().startswith("---"):
                    issues.append(f"Line {line_num}: MD031 Missing blank line after code block")
            continue

        if in_code_block:
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)", raw)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1:
                top_headers += 1
                if top_headers > 1:
                    issues.append(f"Line {line_num}: MD025 Multiple top-level headings: '{text}'")
            # MD026: Trailing punctuation
            if text.endswith(":") or text.endswith("."):
                issues.append(f"Line {line_num}: MD026 Trailing punctuation in heading: '{text}'")
            # MD022: Blank line before heading
            if idx > 0 and lines[idx - 1].strip() != "" and not lines[idx - 1].strip().startswith("---"):
                issues.append(f"Line {line_num}: MD022 Missing blank line before heading")
            # MD022: Blank line after heading
            if idx < len(lines) - 1 and lines[idx + 1].strip() != "":
                issues.append(f"Line {line_num}: MD022 Missing blank line after heading")

        # MD034: Bare URL check
        bare_urls = re.findall(r'(?<![<\(\[])https?://[^\s>\)]+', raw)
        for u in bare_urls:
            issues.append(f"Line {line_num}: MD034 Bare URL: {u}")

    if issues:
        print(f"=== {fname} ({len(issues)} issues) ===")
        for iss in issues:
            print("  ", iss)
    else:
        print(f"=== {fname} (0 issues - CLEAN) ===")
