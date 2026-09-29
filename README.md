# Mileth Crypt Generator

A procedural, branching crypt generator that builds a multi-floor room graph, individual room maps, and an interactive browser-based map.

## Demo

Click the overview image to open the generated interactive map. In the interactive version, select rooms from the overview or sidebar, hover rooms to trace stair connections, and use stairs and room features to explore.

[![Mileth Crypt overview map](output/maps/overview_map.png)](output/dungeon_map.html)

The interactive HTML is generated locally by the script. The PNG above is a static preview for Markdown viewers.

## Run

Requires Python 3 and Matplotlib:

```powershell
python -m pip install matplotlib
python render_dungeon.py
```

The script generates a 30-floor dungeon by default and opens the interactive map in your browser.

## Output

- `output/dungeon_map.html` - interactive room browser with clickable overview rooms, stair-connection highlights, room maps, gate controls, and gathering-node details.
- `output/maps/overview_map.png` - static overview of the generated room graph.
- `output/levels/room_*.png` - rendered image for each generated room.

The generated dungeon includes branching paths, a specially gated lore dead end reached by descending five floors and then ascending, a small spawn-free resting area, and monster spawn markers distributed by room size.
