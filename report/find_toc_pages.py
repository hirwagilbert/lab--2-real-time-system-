"""Locate the printed page number of each TOC heading in the rendered PDF."""
import json, os, re, subprocess
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
pdf = "report/RTS_Unit2_Lab_Report.pdf"
n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout).group(1))
pages = [subprocess.run(["pdftotext", "-layout", "-f", str(i), "-l", str(i), pdf, "-"],
                        capture_output=True, text=True).stdout for i in range(1, n + 1)]
norm = lambda s: re.sub(r"\s+", " ", s).strip()
entries = json.load(open("report/toc_entries.json"))
res, start = {}, 2  # skip cover (1) and the TOC page itself (2)
for e in entries:
    for i in range(start, n):
        lines = [norm(l) for l in pages[i].splitlines()]
        if norm(e) in lines or any(l.startswith(norm(e)) and len(l) < len(norm(e)) + 3 for l in lines):
            # printed page number = physical page (cover counts as page 1)
            res[e] = i + 1
            start = i
            break
    else:
        print("not found:", e)
json.dump(res, open("report/toc_pages.json", "w"), indent=1)
print(res)
