# Dungeon Data Format

`output/data.json` is the renderer-independent dungeon export. It is generated alongside `output/dungeon_map.html` each time `render_dungeon.py` runs. The `schema_version` field identifies the format contract; this document describes version `1.0.0`.

## Coordinate System

- Floors are one-based. Floor 1 is the surface entrance; larger indices are deeper.
- Room tile coordinates use a top-left origin: `x` increases right and `y` increases down.
- `tile_map.rows[y][x]` is the tile symbol at coordinate `{ "x": x, "y": y }`.
- `overview_grid_position` is only the room's position in the 2D overview layout; it is not a room-tile coordinate.
- Suggested Unity position mapping is `(tile_x * tile_size, -floor_index * floor_height, -tile_y * tile_size)`. Choose `tile_size` and `floor_height` in the Unity importer.

## Top-Level Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | Data contract version, currently `1.0.0`. |
| `coordinate_system` | object | Tile origin, axis directions, floor convention, and suggested Unity mapping. |
| `tile_legend` | object | Symbol-to-name-and-color definitions used by the renderer. |
| `dungeon` | object | Dungeon name, counts, floor listing, and critical path. |
| `rooms` | array | Complete room records, including their tilemaps and placed features. |

`dungeon.floors` is ordered by `floor_index`. Each entry lists the room IDs on that floor. `critical_path_room_ids` is ordered from the entrance toward the deepest normal-path room.

## Room Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable room identifier such as `6-2`; unique within the dungeon. |
| `floor_index` | integer | One-based floor depth. |
| `overview_grid_position` | object | `x` room slot and `floor_index` for overview placement. |
| `flags` | object | `main_path`, `dead_end`, `resting_area`, and `lore_room` booleans. |
| `connections` | object | Graph links: `up` contains rooms reached by an up stair; `down` contains rooms reached by a down stair. |
| `tile_map` | object | `width`, `height`, `origin`, and `rows`, an array of equal-length strings. |
| `stairs` | array | Physical stair tile positions, direction, symbol, and destination. |
| `gates` | array | Gate IDs, door tile, lever tile, blocked gate tiles, locked tile count, and optional `down_stair`. |
| `gathering_nodes` | array | Node position, material name, and available amount. Nodes are descriptive props; the HTML demo does not collect them. |
| `monster_spawn_points` | array | Candidate spawn tile positions for a future gameplay system. |

Every feature position is an object with integer `x` and `y`. The complete `tile_map` is authoritative for room geometry; feature arrays add structured metadata for gameplay and prefab placement.

## Tile Symbols

| Symbol | Meaning |
| --- | --- |
| `.` | Floor |
| `#` | Wall |
| `C` | Chest |
| `G` | Gathering node |
| `M` | Monster spawn point |
| `^` | Up stair |
| `v` | Down stair |
| `L` | Lore event |
| `D` | Locked gate door |
| `V` | Gate lever |

Colors and display names are provided in `tile_legend`; Unity can ignore those colors and map symbols to 3D prefabs/materials.

## Stair Destinations

Each stair has:

- `position`: tile coordinate in its room.
- `direction`: `up` or `down`, matching its tile symbol.
- `symbol`: `^` or `v`.
- `destination`: either `{ "kind": "room", "room_id": "..." }` or `{ "kind": "surface" }` for the entrance stair.

Normal room-to-room stairs have a reciprocal stair in the destination room. The secret lore room is an intentional exception to adjacent-floor travel: its only stair leads down to a main-path room five floors deeper, whose up stair returns to it.

## Validation Expectations

A consumer should reject data if:

- `schema_version` is unsupported.
- A room ID is duplicated or referenced by a connection/stair but missing from `rooms`.
- A tile row length differs from `tile_map.width`, or the row count differs from `tile_map.height`.
- A feature coordinate is outside `0 <= x < width` or `0 <= y < height`.
- A stair symbol does not match its `direction`, or its room destination does not exist.

The exported file is self-contained: Unity does not need to parse the HTML, load the PNGs, or reconstruct connections from visual labels.
