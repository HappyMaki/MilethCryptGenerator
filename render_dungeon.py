import os
import json
import base64
import webbrowser
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import ListedColormap
from typing import Tuple, Dict

# Import generator and structures from separate module
from dungeon_generator import generate_procgen_dungeon, DungeonPath, RoomNode, BITMAP_LEGEND

# ==========================================
# DIRECTORY SETUP
# ==========================================

OUTPUT_DIR = "output"
MAPS_DIR = os.path.join(OUTPUT_DIR, "maps")
LEVELS_DIR = os.path.join(OUTPUT_DIR, "levels")


def ensure_directories():
    os.makedirs(MAPS_DIR, exist_ok=True)
    os.makedirs(LEVELS_DIR, exist_ok=True)


# ==========================================
# ISOMETRIC MATH HELPERS
# ==========================================

def grid_to_iso(x: float, y: float, z: float = 0.0) -> Tuple[float, float]:
    """Converts 2D grid coordinates (x, y, z) into 2.5D Isometric screen coordinates."""
    iso_x = (x - y)
    iso_y = (x + y) * 0.5 + z * 0.75
    return iso_x, iso_y


def draw_iso_cube(ax, x, y, z=0, dx=1, dy=1, dz=0.8, face_color="#2b2d42", edge_color="#1a1a24"):
    """Draws a 3D isometric wall block or prop."""
    top_nodes = [
        grid_to_iso(x, y, z + dz),
        grid_to_iso(x + dx, y, z + dz),
        grid_to_iso(x + dx, y + dy, z + dz),
        grid_to_iso(x, y + dy, z + dz)
    ]
    ax.add_patch(
        patches.Polygon(top_nodes, facecolor=face_color, edgecolor=edge_color, linewidth=0.5, zorder=10 + y + x + z))

    left_nodes = [
        grid_to_iso(x, y + dy, z),
        grid_to_iso(x + dx, y + dy, z),
        grid_to_iso(x + dx, y + dy, z + dz),
        grid_to_iso(x, y + dy, z + dz)
    ]
    ax.add_patch(
        patches.Polygon(left_nodes, facecolor="#1c1d28", edgecolor=edge_color, linewidth=0.5, zorder=9 + y + x + z))

    right_nodes = [
        grid_to_iso(x + dx, y, z),
        grid_to_iso(x + dx, y, z),
        grid_to_iso(x + dx, y + dy, z + dz),
        grid_to_iso(x + dx, y, z + dz)
    ]
    ax.add_patch(
        patches.Polygon(right_nodes, facecolor="#14141d", edgecolor=edge_color, linewidth=0.5, zorder=9 + y + x + z))


# ==========================================
# ISOMETRIC ROOM RENDERER
# ==========================================

def render_and_save_iso_room(room: RoomNode) -> str:
    tile_codes = list(BITMAP_LEGEND)
    tile_indexes = {tile: index for index, tile in enumerate(tile_codes)}
    colors = [BITMAP_LEGEND[tile]["color"] for tile in tile_codes]
    grid_height = len(room.bitmap)
    grid_width = len(room.bitmap[0])
    image = [[tile_indexes[tile] for tile in row] for row in room.bitmap]

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.set_facecolor("#101216")
    ax.imshow(image, cmap=ListedColormap(colors), vmin=0, vmax=len(colors) - 1, interpolation="nearest")
    ax.set_axis_off()
    ax.set_xlim(-0.5, grid_width - 0.5)
    ax.set_ylim(grid_height - 0.5, -0.5)

    for y, row in enumerate(room.bitmap):
        for x, tile in enumerate(row):
            if tile not in (".", "#"):
                ax.text(x, y, tile, color="white", fontsize=8, weight="bold", ha="center", va="center")

    legend_handles = [
        patches.Patch(color=details["color"], label=f"{tile}  {details['name']}")
        for tile, details in BITMAP_LEGEND.items()
    ]
    ax.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(1.02, 1), frameon=False,
              labelcolor="white", fontsize=8)

    title_text = f"CRYPT LEVEL {room.room_id}"
    if room.is_dead_end:
        title_text += " [DEAD END]"
    ax.set_title(title_text, color="#f2f4f7", weight="bold", pad=14)
    fig.patch.set_facecolor("#101216")
    plt.tight_layout()

    file_path = os.path.join(LEVELS_DIR, f"room_{room.room_id}.png")
    fig.savefig(file_path, dpi=150, bbox_inches='tight', facecolor='#000000')
    plt.close(fig)
    return file_path


# ==========================================
# OVERVIEW MAP & INTERACTIVE HTML
# ==========================================

def render_and_save_overview_map(dungeon: DungeonPath) -> Tuple[str, str]:
    fig, ax = plt.subplots(figsize=(10, 14))
    ax.set_facecolor("#0b0c10")

    room_coords: Dict[str, Tuple[float, float]] = {}
    floor_height, room_width, room_spacing_x = 2.0, 1.4, 2.2
    max_depth = max(dungeon.floors.keys())

    for depth, rooms in dungeon.floors.items():
        y_pos = (max_depth - depth) * floor_height
        for room in rooms:
            x_pos = room.grid_x * room_spacing_x
            room_coords[room.room_id] = (x_pos + room_width / 2, y_pos + 0.5)

            box_color = "#45a29e" if room.is_main_path else ("#e63946" if room.is_dead_end else "#1f2833")
            edge_color = "#66fcf1" if room.is_main_path else "#0b0c10"

            rect = patches.Rectangle((x_pos, y_pos), room_width, 1.0, linewidth=2, edgecolor=edge_color,
                                     facecolor=box_color, alpha=0.9, zorder=3)
            ax.add_patch(rect)

            label = room.room_id + ("\n(DEAD)" if room.is_dead_end else "")
            ax.text(x_pos + room_width / 2, y_pos + 0.5, label, color="white", weight="bold", fontsize=8, ha="center",
                    va="center", zorder=4)

    for depth, rooms in dungeon.floors.items():
        for room in rooms:
            start_pt = room_coords[room.room_id]
            for target_id in room.connected_to:
                if target_id in room_coords:
                    end_pt = room_coords[target_id]
                    is_critical = room.is_main_path and target_id in dungeon.critical_path

                    if is_critical:
                        ax.plot([start_pt[0], end_pt[0]], [start_pt[1], end_pt[1]],
                                color="#66fcf1", lw=2.5, linestyle="-", zorder=2)
                    else:
                        ax.plot([start_pt[0], end_pt[0]], [start_pt[1], end_pt[1]],
                                color="#f59e0b", lw=2.2, linestyle=(0, (5, 4)), zorder=1, alpha=0.95)

    ax.set_title(dungeon.name + " (Cyan = Critical Path, Orange Dashed = Optional Paths, Red = Dead Ends)",
                 color="#66fcf1", fontsize=10, weight="bold", pad=20)
    ax.axis("off")
    plt.tight_layout()

    file_path = os.path.join(MAPS_DIR, "overview_map.png")
    fig.savefig(file_path, dpi=150, bbox_inches='tight', facecolor='#0b0c10')

    buffer = BytesIO()
    fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='#0b0c10')
    buffer.seek(0)
    b64_str = f"data:image/png;base64,{base64.b64encode(buffer.read()).decode('utf-8')}"

    plt.close(fig)
    return file_path, b64_str


def build_interactive_html(dungeon: DungeonPath):
    ensure_directories()
    overview_path, overview_b64 = render_and_save_overview_map(dungeon)

    for rooms in dungeon.floors.values():
        for room in rooms:
            lvl_path = render_and_save_iso_room(room)
            print(f"Generated Crypt Level -> {lvl_path}")

    room_bitmaps = {
        room.room_id: room.bitmap
        for rooms in dungeon.floors.values()
        for room in rooms
    }
    room_stairs = {
        room.room_id: {f"{x},{y}": target_id for (x, y), target_id in room.stair_destinations.items()}
        for rooms in dungeon.floors.values()
        for room in rooms
    }
    room_gates = {
        room.room_id: {
            gate_id: {
                "tiles": [list(position) for position in gate["tiles"]],
                "door": list(gate["door"]),
                "lever": list(gate["lever"]),
                "locked_tiles": gate["locked_tiles"],
            }
            for gate_id, gate in room.gates.items()
        }
        for rooms in dungeon.floors.values()
        for room in rooms
    }

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{dungeon.name}</title>
    <style>
        body {{ background: #050508; color: #fff; font-family: sans-serif; margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; }}
        h1 {{ color: #66fcf1; margin-bottom: 5px; }}
        .container {{ display: flex; gap: 20px; max-width: 1200px; width: 100%; }}
        .sidebar {{ flex: 1; background: #0b0c10; padding: 15px; border-radius: 8px; border: 1px solid #1f2833; max-height: 800px; overflow-y: auto; }}
        .floor-group {{ margin-bottom: 12px; }}
        .floor-label {{ font-weight: bold; color: #45a29e; margin-bottom: 4px; font-size: 0.85em; }}
        .btn-group {{ display: flex; gap: 6px; flex-wrap: wrap; }}
        button {{ background: #1f2833; color: #c5c6c7; border: 1px solid #45a29e; padding: 6px 10px; border-radius: 4px; cursor: pointer; font-weight: bold; }}
        button:hover, button.active {{ background: #66fcf1; color: #0b0c10; }}
        .btn-back {{ width: 100%; background: #c53030; color: white; border: none; padding: 10px; margin-bottom: 15px; cursor: pointer; border-radius: 4px; font-weight: bold; }}
        .btn-back:hover {{ background: #9b2c2c; }}
        .viewport {{ flex: 3; background: #0b0c10; padding: 15px; border-radius: 8px; border: 1px solid #1f2833; display: flex; justify-content: center; align-items: center; min-height: 600px; }}
        .map-wrapper {{ position: relative; display: inline-block; }}
        img {{ max-width: 100%; max-height: 750px; border-radius: 4px; display: block; }}
        #room-display {{ display: none; max-width: 100%; max-height: 750px; image-rendering: pixelated; }}
        .tile-tooltip {{ display: none; position: absolute; z-index: 5; padding: 6px 8px; color: #fff; background: #050508; border: 1px solid #66fcf1; border-radius: 4px; font-size: 12px; white-space: nowrap; pointer-events: none; }}
        .room-legend {{ display: none; max-width: 900px; flex-wrap: wrap; gap: 8px 14px; padding-top: 10px; color: #c5c6c7; font-size: 12px; }}
        .room-legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
        .legend-swatch {{ width: 12px; height: 12px; border: 1px solid #808894; box-sizing: border-box; }}
    </style>
</head>
<body>
    <h1>{dungeon.name}</h1>
    <p>Select rooms on the left sidebar to navigate through the dungeon levels.</p>
    <div class="container">
        <div class="sidebar">
            <button class="btn-back" onclick="showOverview()">← Back to Overall Map</button>
            <div id="controls"></div>
        </div>
        <div class="viewport">
            <div class="map-wrapper">
                <img id="map-display" src="{overview_b64}">
                <canvas id="room-display" aria-label="Dungeon room map. Click a stair to travel." tabindex="0"></canvas>
                <div id="tile-tooltip" class="tile-tooltip" role="tooltip"></div>
                <div id="room-legend" class="room-legend"></div>
            </div>
        </div>
    </div>
    <script>
        const overviewImage = "{overview_b64}";
        const roomBitmaps = {json.dumps(room_bitmaps)};
        const roomStairs = {json.dumps(room_stairs)};
        const roomGates = {json.dumps(room_gates)};
        const openedGates = Object.fromEntries(Object.keys(roomBitmaps).map(roomId => [roomId, new Set()]));
        const tileLegend = {json.dumps(BITMAP_LEGEND)};
        const floors = {json.dumps({f"Floor {depth}": [r.room_id for r in rooms] for depth, rooms in dungeon.floors.items()})};

        const controlsContainer = document.getElementById('controls');
        const overviewDisplay = document.getElementById('map-display');
        const roomDisplay = document.getElementById('room-display');
        const roomContext = roomDisplay.getContext('2d');
        const tileTooltip = document.getElementById('tile-tooltip');
        const roomLegend = document.getElementById('room-legend');
        const mapWrapper = document.querySelector('.map-wrapper');

        Object.entries(tileLegend).forEach(([symbol, tile]) => {{
            const item = document.createElement('span');
            item.className = 'room-legend-item';
            const swatch = document.createElement('span');
            swatch.className = 'legend-swatch';
            swatch.style.backgroundColor = tile.color;
            item.appendChild(swatch);
            item.appendChild(document.createTextNode(`${{symbol}} ${{tile.name}}`));
            roomLegend.appendChild(item);
        }});

        function drawRoom(roomId) {{
            const bitmap = roomBitmaps[roomId];
            const rows = bitmap.length;
            const columns = bitmap[0].length;
            const cellSize = Math.min(28, 900 / columns, 700 / rows);
            roomDisplay.width = Math.round(columns * cellSize);
            roomDisplay.height = Math.round(rows * cellSize);
            roomContext.textAlign = 'center';
            roomContext.textBaseline = 'middle';
            roomContext.font = `bold ${{Math.max(6, cellSize * 0.48)}}px sans-serif`;

            bitmap.forEach((row, y) => {{
                [...row].forEach((symbol, x) => {{
                    const gateTile = Object.entries(roomGates[roomId] || {{}}).find(([, gate]) =>
                        gate.tiles.some(([gateX, gateY]) => gateX === x && gateY === y)
                    );
                    const displaySymbol = gateTile && openedGates[roomId].has(gateTile[0]) ? '.' : symbol;
                    const tile = tileLegend[displaySymbol];
                    const left = Math.floor(x * roomDisplay.width / columns);
                    const right = Math.floor((x + 1) * roomDisplay.width / columns);
                    const top = Math.floor(y * roomDisplay.height / rows);
                    const bottom = Math.floor((y + 1) * roomDisplay.height / rows);
                    roomContext.fillStyle = tile.color;
                    roomContext.fillRect(left, top, right - left, bottom - top);
                    if (displaySymbol !== '.' && displaySymbol !== '#') {{
                        roomContext.fillStyle = '#fff';
                        roomContext.fillText(displaySymbol, (left + right) / 2, (top + bottom) / 2);
                    }}
                }});
            }});
        }}

        function getRoomTile(event) {{
            const roomId = roomDisplay.dataset.roomId;
            const bitmap = roomBitmaps[roomId];
            if (!bitmap) return null;
            const bounds = roomDisplay.getBoundingClientRect();
            const column = Math.max(0, Math.min(bitmap[0].length - 1, Math.floor((event.clientX - bounds.left) * bitmap[0].length / bounds.width)));
            const row = Math.max(0, Math.min(bitmap.length - 1, Math.floor((event.clientY - bounds.top) * bitmap.length / bounds.height)));
            const symbol = bitmap[row][column];
            const gate = Object.entries(roomGates[roomId] || {{}}).find(([, value]) =>
                value.lever[0] === column && value.lever[1] === row
                || value.door[0] === column && value.door[1] === row
            );
            return {{ roomId, row, column, symbol, destination: roomStairs[roomId]?.[`${{column}},${{row}}`], gateId: gate?.[0], gate: gate?.[1] }};
        }}

        function travelFromStair(tile) {{
            if (!tile.destination) return;
            if (tile.destination === 'Surface') {{
                showOverview();
            }} else {{
                showRoom(tile.destination);
            }}
        }}

        roomDisplay.addEventListener('pointermove', event => {{
            const tile = getRoomTile(event);
            if (!tile) return;
            const {{ roomId, row, column, symbol, destination }} = tile;
            let description = `${{tileLegend[symbol].name}} (${{symbol}})`;
            if (symbol === '^' && destination) description = `Stairs Up to ${{destination}}`;
            if (symbol === 'v' && destination) description = `Stairs Down to ${{destination}}`;
            if (tile.gateId && symbol === 'D') description = openedGates[roomId].has(tile.gateId)
                ? `Gate ${{tile.gateId}} is open`
                : `Gate ${{tile.gateId}} is locked; pull its lever`;
            if (tile.gateId && symbol === 'V') description = `Lever for Gate ${{tile.gateId}}`;
            tileTooltip.textContent = `${{description}} | row ${{row + 1}}, column ${{column + 1}}`;
            roomDisplay.style.cursor = destination ? 'pointer' : 'default';
            roomDisplay.setAttribute('aria-label', destination
                ? `${{description}}. Click to travel.`
                : 'Dungeon room map. Click a stair to travel.');
            const wrapperBounds = mapWrapper.getBoundingClientRect();
            tileTooltip.style.left = `${{event.clientX - wrapperBounds.left + 12}}px`;
            tileTooltip.style.top = `${{event.clientY - wrapperBounds.top + 12}}px`;
            tileTooltip.style.display = 'block';
        }});
        roomDisplay.addEventListener('click', event => {{
            const tile = getRoomTile(event);
            if (!tile) return;
            if (tile.symbol === 'V' && tile.gateId) {{
                openedGates[tile.roomId].add(tile.gateId);
                drawRoom(tile.roomId);
                tileTooltip.textContent = `Gate ${{tile.gateId}} opened | ${{tile.gate.locked_tiles}} floor tiles unlocked`;
                tileTooltip.style.display = 'block';
                return;
            }}
            travelFromStair(tile);
        }});
        roomDisplay.addEventListener('keydown', event => {{
            if ((event.key === 'Enter' || event.key === ' ') && roomDisplay.dataset.focusedStair) {{
                event.preventDefault();
                const [column, row] = roomDisplay.dataset.focusedStair.split(',').map(Number);
                const roomId = roomDisplay.dataset.roomId;
                travelFromStair({{ roomId, column, row, symbol: roomBitmaps[roomId][row][column], destination: roomStairs[roomId][`${{column}},${{row}}`] }});
            }}
        }});
        roomDisplay.addEventListener('pointerleave', () => {{
            tileTooltip.style.display = 'none';
            roomDisplay.style.cursor = 'default';
        }});

        Object.keys(floors).forEach(floorName => {{
            const group = document.createElement('div');
            group.className = 'floor-group';
            const label = document.createElement('div');
            label.className = 'floor-label';
            label.innerText = floorName;
            group.appendChild(label);

            const btnGroup = document.createElement('div');
            btnGroup.className = 'btn-group';

            floors[floorName].forEach(roomId => {{
                const btn = document.createElement('button');
                btn.innerText = roomId;
                btn.id = 'btn-' + roomId;
                btn.onclick = () => showRoom(roomId);
                btnGroup.appendChild(btn);
            }});
            group.appendChild(btnGroup);
            controlsContainer.appendChild(group);
        }});

        function clearActive() {{
            document.querySelectorAll('button').forEach(b => b.classList.remove('active'));
        }}

        function showOverview() {{
            clearActive();
            overviewDisplay.src = overviewImage;
            overviewDisplay.style.display = 'block';
            roomDisplay.style.display = 'none';
            roomLegend.style.display = 'none';
            tileTooltip.style.display = 'none';
        }}

        function showRoom(roomId) {{
            clearActive();
            const btn = document.getElementById('btn-' + roomId);
            if(btn) btn.classList.add('active');
            overviewDisplay.style.display = 'none';
            roomDisplay.style.display = 'block';
            roomDisplay.dataset.roomId = roomId;
            roomLegend.style.display = 'flex';
            tileTooltip.style.display = 'none';
            drawRoom(roomId);
        }}
    </script>
</body>
</html>
"""

    html_file_path = os.path.join(OUTPUT_DIR, "dungeon_map.html")
    with open(html_file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    webbrowser.open(f"file://{os.path.abspath(html_file_path)}")


if __name__ == "__main__":
    # Generate the dungeon graph using dungeon_generator
    dungeon = generate_procgen_dungeon(
        name="Mileth Crypt - Branching Path Maze",
        num_floors=20,
        dead_end_depth_pct=0.65
    )
    # Render and build the interactive HTML viewer
    build_interactive_html(dungeon)