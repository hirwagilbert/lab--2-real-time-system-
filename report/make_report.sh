#!/usr/bin/env bash
# Two-pass build: pass 1 renders the PDF to find heading pages, pass 2 writes them into the TOC.
set -e
cd "$(dirname "$0")/.."
python report/build_report.py
soffice --headless --convert-to pdf --outdir report report/RTS_Unit2_Lab_Report.docx >/dev/null
python report/find_toc_pages.py
python report/build_report.py --toc
soffice --headless --convert-to pdf --outdir report report/RTS_Unit2_Lab_Report.docx >/dev/null
echo "done: report/RTS_Unit2_Lab_Report.pdf"
