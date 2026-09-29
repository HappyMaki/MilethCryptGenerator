import os
import json
import base64
import webbrowser
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import ListedColormap
from typing import Tuple, Dict, List

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


def export_dungeon_data(dungeon: DungeonPath) -> str:
    coordinate = lambda position: {"x": position[0], "y": position[1]}
    room_data = []

    for floor_index, rooms in sorted(dungeon.floors.items()):
        for room in rooms:
            stairs = []
            for position, destination in sorted(room.stair_destinations.items()):
                symbol = room.bitmap[position[1]][position[0]]
                stairs.append({
                    "position": coordinate(position),
                    "direction": "up" if symbol == "^" else "down",
                    "symbol": symbol,
                    "destination": {"kind": "surface"} if destination == "Surface" else {
                        "kind": "room",
                        "room_id": destination,
                    },
                })

            gates = []
            for gate_id, gate in sorted(room.gates.items()):
                gate_data = {
                    "id": gate_id,
                    "door": coordinate(gate["door"]),
                    "lever": coordinate(gate["lever"]),
                    "tiles": [coordinate(position) for position in gate["tiles"]],
                    "locked_tile_count": gate["locked_tiles"],
                }
                if "down_stair" in gate:
                    gate_data["down_stair"] = coordinate(gate["down_stair"])
                gates.append(gate_data)

            room_data.append({
                "id": room.room_id,
                "floor_index": floor_index,
                "overview_grid_position": {
                    "x": room.grid_x,
                    "floor_index": floor_index,
                },
                "flags": {
                    "main_path": room.is_main_path,
                    "dead_end": room.is_dead_end,
                    "resting_area": room.is_resting_area,
                    "lore_room": room.is_lore_room,
                },
                "connections": {
                    "up": list(room.connected_from),
                    "down": list(room.connected_to),
                },
                "tile_map": {
                    "width": len(room.bitmap[0]),
                    "height": len(room.bitmap),
                    "origin": "top_left",
                    "rows": room.bitmap,
                },
                "stairs": stairs,
                "gates": gates,
                "gathering_nodes": [
                    {
                        "position": coordinate(position),
                        "material": node["material"],
                        "amount": node["amount"],
                    }
                    for position, node in sorted(room.gathering_nodes.items())
                ],
                "monster_spawn_points": [
                    coordinate(position)
                    for position in sorted(room.monster_spawn_points)
                ],
            })

    data = {
        "schema_version": "1.0.0",
        "coordinate_system": {
            "tile_origin": "top_left",
            "tile_x_axis": "right",
            "tile_y_axis": "down",
            "floor_indexing": "1_based_increases_deeper",
            "unity_position_mapping": "(tile_x * tile_size, -floor_index * floor_height, -tile_y * tile_size)",
        },
        "tile_legend": BITMAP_LEGEND,
        "dungeon": {
            "name": dungeon.name,
            "floor_count": len(dungeon.floors),
            "room_count": len(room_data),
            "critical_path_room_ids": list(dungeon.critical_path),
            "floors": [
                {
                    "floor_index": floor_index,
                    "room_ids": [room.room_id for room in rooms],
                }
                for floor_index, rooms in sorted(dungeon.floors.items())
            ],
        },
        "rooms": room_data,
    }

    data_path = os.path.join(OUTPUT_DIR, "data.json")
    with open(data_path, "w", encoding="utf-8") as data_file:
        json.dump(data, data_file, ensure_ascii=False, indent=2)
        data_file.write("\n")
    return data_path


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
                label_color = "#101216" if tile in ("^", "v") else "white"
                ax.text(x, y, tile, color=label_color, fontsize=8, weight="bold", ha="center", va="center")

    legend_handles = [
        patches.Patch(color=details["color"], label=f"{tile}  {details['name']}")
        for tile, details in BITMAP_LEGEND.items()
    ]
    ax.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(1.02, 1), frameon=False,
              labelcolor="white", fontsize=8)

    title_text = f"CRYPT LEVEL {room.room_id}"
    if room.is_resting_area:
        title_text += " [REST AREA]"
    if room.is_lore_room:
        title_text += " [LORE ROOM]"
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

def render_and_save_overview_map(dungeon: DungeonPath) -> Tuple[str, str, List[Dict[str, object]]]:
    fig, ax = plt.subplots(figsize=(10, 14))
    ax.set_facecolor("#0b0c10")

    room_coords: Dict[str, Tuple[float, float]] = {}
    room_boxes: Dict[str, Tuple[float, float, float, float]] = {}
    floor_height, room_width, room_spacing_x = 2.0, 1.4, 2.2
    max_depth = max(dungeon.floors.keys())

    for depth, rooms in dungeon.floors.items():
        y_pos = (max_depth - depth) * floor_height
        for room in rooms:
            x_pos = room.grid_x * room_spacing_x
            room_coords[room.room_id] = (x_pos + room_width / 2, y_pos + 0.5)
            room_boxes[room.room_id] = (x_pos, y_pos, room_width, 1.0)

            box_color = "#45a29e" if room.is_main_path else ("#e63946" if room.is_dead_end else "#1f2833")
            edge_color = "#66fcf1" if room.is_main_path else "#0b0c10"

            rect = patches.Rectangle((x_pos, y_pos), room_width, 1.0, linewidth=2, edgecolor=edge_color,
                                     facecolor=box_color, alpha=0.9, zorder=3)
            ax.add_patch(rect)

            label = room.room_id + (" *" if room.is_resting_area else "") + (" L" if room.is_lore_room else "")
            ax.text(x_pos + room_width / 2, y_pos + 0.5, label, color="white", weight="bold", fontsize=11, ha="center",
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

    # Split the heading so neither line runs wide enough to be downscaled into mush.
    ax.set_title(dungeon.name, color="#66fcf1", fontsize=14, weight="bold", pad=26)
    ax.text(
        0.5, 1.0,
        "Cyan = Critical Path   Orange Dashed = Optional Paths   Red = Dead Ends   "
        "* = Rest Area   L = Lore Dead End",
        transform=ax.transAxes, color="#66fcf1", fontsize=8, ha="center", va="bottom",
    )
    ax.axis("off")
    plt.tight_layout()

    output_dpi = 150
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tight_bbox = fig.get_tightbbox(renderer)
    padding = plt.rcParams["savefig.pad_inches"]
    crop_left = (tight_bbox.x0 - padding) * output_dpi
    crop_top = (tight_bbox.y1 + padding) * output_dpi
    crop_width = (tight_bbox.width + 2 * padding) * output_dpi
    crop_height = (tight_bbox.height + 2 * padding) * output_dpi
    pixel_scale = output_dpi / fig.dpi
    # Room rectangles are stroked with linewidth=2 centred on their edge, so the ink
    # extends half a point beyond the data bounds. Grow each hover box to cover that
    # ink; otherwise the highlight sits a couple of pixels inside the box it outlines,
    # which reads as the left column leaning right and the right column leaning left.
    stroke_margin = 1.0 / 72.0 * output_dpi
    room_hotspots = []
    for room_id, (x_pos, y_pos, box_width, box_height) in room_boxes.items():
        top_left = ax.transData.transform((x_pos, y_pos + box_height))
        bottom_right = ax.transData.transform((x_pos + box_width, y_pos))
        left_px = top_left[0] * pixel_scale - crop_left - stroke_margin
        top_px = crop_top - top_left[1] * pixel_scale - stroke_margin
        width_px = (bottom_right[0] - top_left[0]) * pixel_scale + 2 * stroke_margin
        height_px = (top_left[1] - bottom_right[1]) * pixel_scale + 2 * stroke_margin
        room_hotspots.append({
            "room_id": room_id,
            "left": left_px / crop_width * 100,
            "top": top_px / crop_height * 100,
            "width": width_px / crop_width * 100,
            "height": height_px / crop_height * 100,
        })

    file_path = os.path.join(MAPS_DIR, "overview_map.png")
    fig.savefig(file_path, dpi=output_dpi, bbox_inches='tight', facecolor='#0b0c10')

    buffer = BytesIO()
    fig.savefig(buffer, format='png', dpi=output_dpi, bbox_inches='tight', facecolor='#0b0c10')
    buffer.seek(0)
    b64_str = f"data:image/png;base64,{base64.b64encode(buffer.read()).decode('utf-8')}"

    plt.close(fig)
    return file_path, b64_str, room_hotspots


def build_interactive_html(dungeon: DungeonPath):
    ensure_directories()
    data_path = export_dungeon_data(dungeon)
    print(f"Generated Dungeon Data -> {data_path}")
    overview_path, overview_b64, room_hotspots = render_and_save_overview_map(dungeon)

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
    room_connections = {
        room.room_id: {"up": room.connected_from, "down": room.connected_to}
        for rooms in dungeon.floors.values()
        for room in rooms
    }
    room_gathering_nodes = {
        room.room_id: {
            f"{x},{y}": node
            for (x, y), node in room.gathering_nodes.items()
        }
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
        .btn-overview {{ width: 100%; padding: 12px; margin-bottom: 15px; }}
        .viewport {{ position: relative; flex: 3; background: #0b0c10; padding: 15px; border-radius: 8px; border: 1px solid #1f2833; display: flex; justify-content: center; align-items: center; min-height: 900px; overflow: hidden; touch-action: none; cursor: grab; }}
        .viewport.dragging, .viewport.dragging * {{ cursor: grabbing !important; user-select: none; }}
        .map-navigation {{ position: absolute; z-index: 10; top: 12px; right: 12px; display: flex; gap: 4px; }}
        .map-navigation button {{ min-width: 34px; height: 32px; padding: 0 8px; }}
        #zoom-reset {{ min-width: 52px; font-size: 11px; }}
        .map-wrapper {{ position: relative; display: inline-block; transform-origin: 0 0; will-change: transform; }}
        .overview-wrapper {{ position: relative; display: inline-block; line-height: 0; }}
        #map-hotspots {{ position: absolute; inset: 0; pointer-events: none; }}
        .map-connection-overlay {{ position: absolute; inset: 0; z-index: 1; width: 100%; height: 100%; overflow: visible; pointer-events: none; }}
        .map-connection {{ fill: none; stroke-width: 2.8; vector-effect: non-scaling-stroke; filter: drop-shadow(0 0 3px #050508); }}
        .map-connection.up {{ stroke: #f59e0b; }}
        .map-connection.down {{ stroke: #66fcf1; }}
        .map-hotspot {{ position: absolute; z-index: 2; box-sizing: border-box; min-width: 0; min-height: 0; padding: 0; border: 0; border-radius: 1px; background: transparent; color: transparent; font-size: 0; pointer-events: auto; }}
        .map-hotspot:hover, .map-hotspot:focus-visible {{ background: rgba(102, 252, 241, 0.18); border-color: #66fcf1; outline: 2px solid #66fcf1; outline-offset: 1px; }}
        img {{ max-width: 100%; max-height: 1100px; border-radius: 4px; display: block; }}
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
            <button class="btn-overview" onclick="showOverview()">Overall Map Layout</button>
            <div id="controls"></div>
        </div>
        <div class="viewport">
            <div class="map-navigation" role="group" aria-label="Map zoom controls">
                <button id="zoom-out" type="button" aria-label="Zoom out" title="Zoom out">−</button>
                <button id="zoom-reset" type="button" aria-label="Reset zoom" title="Reset zoom">100%</button>
                <button id="zoom-in" type="button" aria-label="Zoom in" title="Zoom in">+</button>
            </div>
            <div class="map-wrapper">
                <div id="overview-wrapper" class="overview-wrapper">
                    <img id="map-display" src="{overview_b64}">
                    <div id="map-hotspots" role="group" aria-label="Clickable rooms on the overall map"></div>
                </div>
                <canvas id="room-display" aria-label="Dungeon room map. Click a stair to travel." tabindex="0"></canvas>
                <div id="tile-tooltip" class="tile-tooltip" role="tooltip"></div>
                <div id="room-legend" class="room-legend"></div>
            </div>
        </div>
    </div>
    <script>
        const overviewImage = "{overview_b64}";
        const overviewHotspots = {json.dumps(room_hotspots)};
        const roomConnections = {json.dumps(room_connections)};
        const roomBitmaps = {json.dumps(room_bitmaps)};
        const roomStairs = {json.dumps(room_stairs)};
        const roomGatheringNodes = {json.dumps(room_gathering_nodes)};
        const roomGates = {json.dumps(room_gates)};
        const openedGates = Object.fromEntries(Object.keys(roomBitmaps).map(roomId => [roomId, new Set()]));
        const tileLegend = {json.dumps(BITMAP_LEGEND)};
        const floors = {json.dumps({f"Floor {depth}": [r.room_id for r in rooms] for depth, rooms in dungeon.floors.items()})};
        const restingRooms = new Set({json.dumps([room.room_id for rooms in dungeon.floors.values() for room in rooms if room.is_resting_area])});
        const loreRooms = new Set({json.dumps([room.room_id for rooms in dungeon.floors.values() for room in rooms if room.is_lore_room])});

        const controlsContainer = document.getElementById('controls');
        const overviewWrapper = document.getElementById('overview-wrapper');
        const overviewDisplay = document.getElementById('map-display');
        const mapHotspots = document.getElementById('map-hotspots');
        const roomDisplay = document.getElementById('room-display');
        const roomContext = roomDisplay.getContext('2d');
        const tileTooltip = document.getElementById('tile-tooltip');
        const roomLegend = document.getElementById('room-legend');
        const mapWrapper = document.querySelector('.map-wrapper');
        const viewport = document.querySelector('.viewport');
        const zoomOutButton = document.getElementById('zoom-out');
        const zoomResetButton = document.getElementById('zoom-reset');
        const zoomInButton = document.getElementById('zoom-in');
        let mapZoom = 1;
        let mapPanX = 0;
        let mapPanY = 0;
        let activePan = null;
        let suppressMapClick = false;

        function applyMapTransform() {{
            const viewportStyle = getComputedStyle(viewport);
            const availableWidth = viewport.clientWidth - parseFloat(viewportStyle.paddingLeft) - parseFloat(viewportStyle.paddingRight);
            const availableHeight = viewport.clientHeight - parseFloat(viewportStyle.paddingTop) - parseFloat(viewportStyle.paddingBottom);
            const maxPanX = Math.max(0, (mapWrapper.offsetWidth * mapZoom - availableWidth) / 2);
            const maxPanY = Math.max(0, (mapWrapper.offsetHeight * mapZoom - availableHeight) / 2);
            mapPanX = Math.max(-maxPanX, Math.min(maxPanX, mapPanX));
            mapPanY = Math.max(-maxPanY, Math.min(maxPanY, mapPanY));
            mapWrapper.style.transform = `translate(${{mapPanX}}px, ${{mapPanY}}px) scale(${{mapZoom}})`;
            zoomResetButton.textContent = `${{Math.round(mapZoom * 100)}}%`;
        }}

        function zoomAt(nextZoom, clientX, clientY) {{
            nextZoom = Math.max(1, Math.min(4, nextZoom));
            const bounds = mapWrapper.getBoundingClientRect();
            const localX = (clientX - bounds.left) / mapZoom;
            const localY = (clientY - bounds.top) / mapZoom;
            const baseLeft = bounds.left - mapPanX;
            const baseTop = bounds.top - mapPanY;
            mapPanX = clientX - baseLeft - localX * nextZoom;
            mapPanY = clientY - baseTop - localY * nextZoom;
            mapZoom = nextZoom;
            applyMapTransform();
        }}

        function zoomAtCenter(nextZoom) {{
            const bounds = viewport.getBoundingClientRect();
            zoomAt(nextZoom, bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
        }}

        viewport.addEventListener('wheel', event => {{
            event.preventDefault();
            zoomAt(mapZoom * Math.exp(-event.deltaY * 0.001), event.clientX, event.clientY);
        }}, {{ passive: false }});
        viewport.addEventListener('pointerdown', event => {{
            if (event.button !== 0 || event.target.closest('.map-navigation')) return;
            activePan = {{
                pointerId: event.pointerId,
                startX: event.clientX,
                startY: event.clientY,
                startPanX: mapPanX,
                startPanY: mapPanY,
                moved: false,
            }};
        }});
        viewport.addEventListener('pointermove', event => {{
            if (!activePan || activePan.pointerId !== event.pointerId) return;
            const deltaX = event.clientX - activePan.startX;
            const deltaY = event.clientY - activePan.startY;
            if (!activePan.moved && Math.hypot(deltaX, deltaY) < 4) return;
            if (!activePan.moved) {{
                activePan.moved = true;
                viewport.setPointerCapture(event.pointerId);
                viewport.classList.add('dragging');
                tileTooltip.style.display = 'none';
                clearRoomConnections();
            }}
            mapPanX = activePan.startPanX + deltaX;
            mapPanY = activePan.startPanY + deltaY;
            applyMapTransform();
        }});
        function finishMapPan(event) {{
            if (!activePan || activePan.pointerId !== event.pointerId) return;
            if (activePan.moved) {{
                suppressMapClick = true;
                setTimeout(() => {{ suppressMapClick = false; }}, 0);
            }}
            activePan = null;
            viewport.classList.remove('dragging');
        }}
        viewport.addEventListener('pointerup', finishMapPan);
        viewport.addEventListener('pointercancel', finishMapPan);
        viewport.addEventListener('click', event => {{
            if (!suppressMapClick) return;
            suppressMapClick = false;
            event.preventDefault();
            event.stopPropagation();
        }}, true);
        zoomInButton.addEventListener('click', () => zoomAtCenter(mapZoom * 1.25));
        zoomOutButton.addEventListener('click', () => zoomAtCenter(mapZoom / 1.25));
        zoomResetButton.addEventListener('click', () => {{
            mapZoom = 1;
            mapPanX = 0;
            mapPanY = 0;
            applyMapTransform();
        }});
        window.addEventListener('resize', applyMapTransform);
        applyMapTransform();
        const hotspotsByRoom = Object.fromEntries(overviewHotspots.map(hotspot => [hotspot.room_id, hotspot]));
        const svgNamespace = 'http://www.w3.org/2000/svg';
        const connectionOverlay = document.createElementNS(svgNamespace, 'svg');
        connectionOverlay.classList.add('map-connection-overlay');
        connectionOverlay.setAttribute('viewBox', '0 0 100 100');
        connectionOverlay.setAttribute('preserveAspectRatio', 'none');
        const connectionDefinitions = document.createElementNS(svgNamespace, 'defs');
        [['up', '#f59e0b'], ['down', '#66fcf1']].forEach(([direction, color]) => {{
            const marker = document.createElementNS(svgNamespace, 'marker');
            marker.id = `connection-arrow-${{direction}}`;
            marker.setAttribute('viewBox', '0 0 8 8');
            marker.setAttribute('refX', '7');
            marker.setAttribute('refY', '4');
            marker.setAttribute('markerWidth', '4');
            marker.setAttribute('markerHeight', '4');
            marker.setAttribute('markerUnits', 'strokeWidth');
            marker.setAttribute('orient', 'auto');
            const arrow = document.createElementNS(svgNamespace, 'path');
            arrow.setAttribute('d', 'M 0 0 L 8 4 L 0 8 z');
            arrow.setAttribute('fill', color);
            marker.appendChild(arrow);
            connectionDefinitions.appendChild(marker);
        }});
        connectionOverlay.appendChild(connectionDefinitions);
        mapHotspots.appendChild(connectionOverlay);

        function showRoomConnections(roomId) {{
            const source = hotspotsByRoom[roomId];
            if (!source) return;
            connectionOverlay.replaceChildren(connectionDefinitions);
            const sourceX = source.left + source.width / 2;
            const sourceY = source.top + source.height / 2;
            const connections = roomConnections[roomId] || {{ up: [], down: [] }};
            ['up', 'down'].forEach(direction => {{
                connections[direction].forEach(targetId => {{
                    const target = hotspotsByRoom[targetId];
                    if (!target) return;
                    const line = document.createElementNS(svgNamespace, 'line');
                    line.classList.add('map-connection', direction);
                    line.setAttribute('x1', sourceX);
                    line.setAttribute('y1', sourceY);
                    line.setAttribute('x2', target.left + target.width / 2);
                    line.setAttribute('y2', target.top + target.height / 2);
                    line.setAttribute('marker-end', `url(#connection-arrow-${{direction}})`);
                    connectionOverlay.appendChild(line);
                }});
            }});
        }}

        function clearRoomConnections() {{
            connectionOverlay.replaceChildren(connectionDefinitions);
        }}

        overviewHotspots.forEach(hotspot => {{
            const roomId = hotspot.room_id;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'map-hotspot';
            button.title = `Open ${{roomId}}${{restingRooms.has(roomId) ? ' (rest area)' : ''}}${{loreRooms.has(roomId) ? ' (lore dead end)' : ''}}`;
            button.setAttribute('aria-label', button.title);
            button.style.left = `${{hotspot.left}}%`;
            button.style.top = `${{hotspot.top}}%`;
            button.style.width = `${{hotspot.width}}%`;
            button.style.height = `${{hotspot.height}}%`;
            button.addEventListener('click', () => showRoom(roomId));
            button.addEventListener('pointerenter', () => showRoomConnections(roomId));
            button.addEventListener('pointerleave', clearRoomConnections);
            button.addEventListener('focus', () => showRoomConnections(roomId));
            button.addEventListener('blur', clearRoomConnections);
            mapHotspots.appendChild(button);
        }});

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
                        roomContext.fillStyle = displaySymbol === '^' || displaySymbol === 'v' ? '#101216' : '#fff';
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
            const nodeKey = `${{column}},${{row}}`;
            return {{
                roomId,
                row,
                column,
                symbol,
                destination: roomStairs[roomId]?.[nodeKey],
                gateId: gate?.[0],
                gate: gate?.[1],
                gatheringNode: roomGatheringNodes[roomId]?.[nodeKey],
            }};
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
            const {{ roomId, row, column, symbol, destination, gatheringNode }} = tile;
            // Plain floor carries no information, so hovering it shows no tooltip.
            if (symbol === '.') {{
                tileTooltip.style.display = 'none';
                roomDisplay.style.cursor = 'default';
                return;
            }}
            let description = `${{tileLegend[symbol].name}} (${{symbol}})`;
            if (symbol === '^' && destination) description = `Stairs Up to ${{destination}}`;
            if (symbol === 'v' && destination) description = `Stairs Down to ${{destination}}`;
            if (symbol === 'G' && gatheringNode) description = `${{gatheringNode.material}} resource node`;
            if (tile.gateId && symbol === 'D') description = openedGates[roomId].has(tile.gateId)
                ? `Gate ${{tile.gateId}} is open`
                : `Gate ${{tile.gateId}} is locked; pull its lever`;
            if (tile.gateId && symbol === 'V') description = `Lever for Gate ${{tile.gateId}}`;
            tileTooltip.textContent = `${{description}} | row ${{row + 1}}, column ${{column + 1}}`;
            roomDisplay.style.cursor = destination ? 'pointer' : 'default';
            roomDisplay.setAttribute('aria-label', destination
                ? `${{description}}. Click to travel.`
                : 'Dungeon room map. Hover over tiles to inspect them; click stairs to travel.');
            const wrapperBounds = mapWrapper.getBoundingClientRect();
            tileTooltip.style.left = `${{(event.clientX - wrapperBounds.left) / mapZoom + 12}}px`;
            tileTooltip.style.top = `${{(event.clientY - wrapperBounds.top) / mapZoom + 12}}px`;
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
                btn.innerText = roomId + (restingRooms.has(roomId) ? ' *' : '') + (loreRooms.has(roomId) ? ' L' : '');
                btn.id = 'btn-' + roomId;
                const connections = roomConnections[roomId] || {{ up: [], down: [] }};
                btn.title = `Stairs up: ${{connections.up.join(', ') || 'none'}}; down: ${{connections.down.join(', ') || 'none'}}`;
                btn.addEventListener('pointerenter', () => showRoomConnections(roomId));
                btn.addEventListener('pointerleave', clearRoomConnections);
                btn.addEventListener('focus', () => showRoomConnections(roomId));
                btn.addEventListener('blur', clearRoomConnections);
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
            overviewWrapper.style.display = 'inline-block';
            overviewDisplay.style.display = 'block';
            roomDisplay.style.display = 'none';
            roomLegend.style.display = 'none';
            tileTooltip.style.display = 'none';
            applyMapTransform();
        }}

        function showRoom(roomId) {{
            clearActive();
            const btn = document.getElementById('btn-' + roomId);
            if(btn) btn.classList.add('active');
            overviewWrapper.style.display = 'none';
            overviewDisplay.style.display = 'none';
            roomDisplay.style.display = 'block';
            roomDisplay.dataset.roomId = roomId;
            roomLegend.style.display = 'flex';
            tileTooltip.style.display = 'none';
            drawRoom(roomId);
            applyMapTransform();
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
        num_floors=30,
        dead_end_depth_pct=0.65
    )
    # Render and build the interactive HTML viewer
    build_interactive_html(dungeon)