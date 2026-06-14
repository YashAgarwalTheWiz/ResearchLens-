from config import HEAD_CHARS,TAIL_CHARS

def text_sections(combined,head_chars=HEAD_CHARS,tail_chars=TAIL_CHARS):
    head=combined[:head_chars]
    ref_index=combined.lower().rfind('references')
    if ref_index!=-1:
        tail_start=max(0,ref_index-tail_chars)
        tail=combined[tail_start:ref_index]
    else:
        tail_start=max(0,len(combined)-tail_chars)
        tail=combined[tail_start:]
    
    middle=combined[head_chars:tail_start] if head_chars<tail_start else ""

    return {'head':head,'middle':middle,'tail':tail}
