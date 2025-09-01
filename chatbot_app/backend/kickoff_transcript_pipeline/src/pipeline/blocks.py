from typing import List, Dict, Any, Iterable


def partition_by_minutes(segments: List[Dict[str, Any]], minutes_per_block: int) -> List[List[Dict[str, Any]]]:
    if minutes_per_block <= 0:
        return [segments]
    block_sec = minutes_per_block * 60
    blocks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_block_index = 0

    for seg in sorted(segments, key=lambda s: int(s.get("t_start") or s.get("t") or 0)):
        t = int(seg.get("t_start") or seg.get("t") or 0)
        idx = t // block_sec
        if idx != current_block_index:
            blocks.append(current)
            current = []
            current_block_index = idx
        current.append(seg)
    if current:
        blocks.append(current)
    return blocks


def select_block(blocks: List[List[Dict[str, Any]]], block_index: int) -> List[Dict[str, Any]]:
    if block_index < 0 or block_index >= len(blocks):
        return []
    return blocks[block_index]
