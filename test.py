from services.text_sections import text_sections

# Case 1: normal paper with a references section
paper = ("Introduction content " * 500) + "References\n" + ("Ref item " * 200)
result = text_sections(paper)
print("head:", len(result["head"]))
print("tail:", len(result["tail"]))
print("middle:", len(result["middle"]))

# Case 2: short paper — does middle come back empty?
short = "Intro. Method. Result. References. Bib."
result2 = text_sections(short, head_chars=50, tail_chars=10)
print("short paper middle:", repr(result2["middle"]))