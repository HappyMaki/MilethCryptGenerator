import random
from collections import deque
from typing import List, Dict, Optional, Tuple


BITMAP_LEGEND = {
    ".": {"name": "Floor", "color": "#454744"},
    "#": {"name": "Wall", "color": "#242b2a"},
    "C": {"name": "Chest", "color": "#b0974f"},
    "T": {"name": "Torch", "color": "#b46f3d"},
    "^": {"name": "Stairs Up", "color": "#60846e"},
    "v": {"name": "Stairs Down", "color": "#925c58"},
    "L": {"name": "Lore Event", "color": "#647b8a"},
    "D": {"name": "Locked Gate", "color": "#a34e43"},
    "V": {"name": "Gate Lever", "color": "#c49a52"},
}


class RoomNode:
    """Represents an individual room or node in the dungeon network."""
    def __init__(self, room_id: str, floor_index: int, grid_x: int, is_main_path: bool = False):
        self.room_id = room_id
        self.floor_index = floor_index
        self.grid_x = grid_x
        self.is_main_path = is_main_path
        self.is_dead_end = False
        self.connected_to: List[str] = []    # Stair connections leading Down
        self.connected_from: List[str] = []  # Stair connections leading Up
        self.bitmap: List[str] = []
        self.stair_destinations: Dict[Tuple[int, int], str] = {}
        self.gates: Dict[str, Dict[str, object]] = {}


class DungeonPath:
    """Container data structure for the entire dungeon layout graph."""
    def __init__(self, name: str):
        self.name = name
        self.floors: Dict[int, List[RoomNode]] = {}
        self.critical_path: List[str] = []


def generate_procgen_dungeon(
    name: str = "Mileth Crypt Path",
    num_floors: int = 10,
    dead_end_depth_pct: float = 0.65,
    seed: Optional[int] = None
) -> DungeonPath:
    """
    Generates a procedural dungeon topology with a guaranteed critical path,
    optional branching paths, restricted deep dead ends, and orphan pruning.
    """
    dungeon = DungeonPath(name)
    rng = random.Random(seed)

    # Floor depth threshold where dead ends start appearing (e.g., floor >= 4 on a 10-floor dungeon)
    min_dead_end_floor = int(num_floors * (1.0 - dead_end_depth_pct)) + 1

    # 1. Instantiate Rooms per floor
    for floor in range(1, num_floors + 1):
        dungeon.floors[floor] = []
        room_count = 1 if (floor == 1 or floor == num_floors) else rng.randint(2, 4)
        main_x = rng.randint(0, room_count - 1)

        for x in range(room_count):
            room_id = f"{floor}-{x + 1}"
            is_main = (x == main_x)
            node = RoomNode(room_id, floor, x, is_main)
            dungeon.floors[floor].append(node)

            if is_main:
                dungeon.critical_path.append(room_id)

    # 2. Connect Critical Main Path Downward
    for floor in range(1, num_floors):
        upper_main_id = dungeon.critical_path[floor - 1]
        lower_main_id = dungeon.critical_path[floor]

        upper_node = next(r for r in dungeon.floors[floor] if r.room_id == upper_main_id)
        upper_node.connected_to.append(lower_main_id)

    # 3. Connect Non-Main Rooms with Depth Threshold Constraint
    for floor in range(1, num_floors):
        upper_rooms = dungeon.floors[floor]
        lower_rooms = dungeon.floors[floor + 1]

        for room in upper_rooms:
            if room.is_main_path:
                # Critical path rooms can branch off to lower non-main rooms
                non_main_below = [r for r in lower_rooms if not r.is_main_path]
                if non_main_below and rng.random() < 0.6:
                    target = rng.choice(non_main_below)
                    if target.room_id not in room.connected_to:
                        room.connected_to.append(target.room_id)
            else:
                # TOP SAFE ZONE: Force non-main rooms to connect down to avoid high-level dead ends
                if floor < min_dead_end_floor:
                    target = lower_rooms[min(room.grid_x, len(lower_rooms) - 1)]
                    if target.room_id not in room.connected_to:
                        room.connected_to.append(target.room_id)
                # BOTTOM DEEP ZONE: Allow chance to connect down or terminate as a dead end
                else:
                    if rng.random() < 0.4:
                        target = rng.choice(lower_rooms)
                        if target.room_id not in room.connected_to:
                            room.connected_to.append(target.room_id)

    # 4. BFS REACHABILITY PASS: Prune Unreachable (Orphaned) Rooms
    all_rooms = {room.room_id: room for depth in dungeon.floors.values() for room in depth}
    start_room_id = dungeon.critical_path[0]

    reachable_ids = set()
    queue = deque([start_room_id])

    while queue:
        curr_id = queue.popleft()
        if curr_id in reachable_ids:
            continue
        reachable_ids.add(curr_id)
        curr_room = all_rooms[curr_id]
        for target_id in curr_room.connected_to:
            if target_id not in reachable_ids:
                queue.append(target_id)

    # Remove unreachable rooms from floor lists
    for floor in list(dungeon.floors.keys()):
        dungeon.floors[floor] = [r for r in dungeon.floors[floor] if r.room_id in reachable_ids]

    room_id_map = {}
    for floor in dungeon.floors.keys():
        for idx, room in enumerate(dungeon.floors[floor]):
            new_room_id = f"{floor}-{idx + 1}"
            room_id_map[room.room_id] = new_room_id
            room.grid_x = idx

    for rooms in dungeon.floors.values():
        for room in rooms:
            room.room_id = room_id_map[room.room_id]
            room.connected_to = [room_id_map[target_id] for target_id in room.connected_to]
    dungeon.critical_path = [room_id_map[room_id] for room_id in dungeon.critical_path]

    # 5. Mark Dead End Flags & Populate Upward Connections
    for floor in range(1, num_floors + 1):
        for room in dungeon.floors[floor]:
            # Clean connections targeting pruned rooms
            room.connected_to = [t_id for t_id in room.connected_to if t_id in reachable_ids]

            if not room.connected_to and floor != num_floors:
                room.is_dead_end = True

    for floor in range(1, num_floors):
        for room in dungeon.floors[floor]:
            for target_id in room.connected_to:
                target_room = next((r for r in dungeon.floors[floor + 1] if r.room_id == target_id), None)
                if target_room and room.room_id not in target_room.connected_from:
                    target_room.connected_from.append(room.room_id)

    for floor, rooms in dungeon.floors.items():
        for room in rooms:
            room.bitmap = _generate_room_bitmap(room, rng)

    return dungeon


def _generate_room_bitmap(room: RoomNode, rng: random.Random) -> List[str]:
    if room.floor_index <= 3 or rng.random() < 0.1:
        minimum_dimension, maximum_dimension = 20, 40
    else:
        minimum_dimension, maximum_dimension = 80, 120
    width = rng.randint(minimum_dimension, maximum_dimension)
    height = rng.randint(minimum_dimension, maximum_dimension)
    bitmap = [["#" for _ in range(width)] for _ in range(height)]
    for tile_x in range(width):
        bitmap[0][tile_x] = "#"
        bitmap[height - 1][tile_x] = "#"
    for tile_y in range(height):
        bitmap[tile_y][0] = "#"
        bitmap[tile_y][width - 1] = "#"

    target_room_count = max(1, min(24, width * height // 400))
    rooms: List[Dict[str, int]] = []
    room_floor_tiles: List[Tuple[int, int]] = []
    door_walls = set()
    door_tiles = set()
    doorways: List[frozenset[Tuple[int, int]]] = []

    regions = [(2, 2, width - 3, height - 3)]
    while len(regions) < target_room_count:
        splittable = []
        for region_index, (region_left, region_top, region_right, region_bottom) in enumerate(regions):
            region_width = region_right - region_left + 1
            region_height = region_bottom - region_top + 1
            can_split_x = region_width >= 36
            can_split_y = region_height >= 36
            if can_split_x or can_split_y:
                splittable.append((region_width * region_height, region_index, can_split_x, can_split_y))
        if not splittable:
            break

        _, region_index, can_split_x, can_split_y = max(splittable)
        region_left, region_top, region_right, region_bottom = regions.pop(region_index)
        region_width = region_right - region_left + 1
        region_height = region_bottom - region_top + 1
        split_x = can_split_x and (not can_split_y or region_width > region_height)
        if can_split_x and can_split_y and region_width == region_height:
            split_x = rng.choice((True, False))
        if split_x:
            split = rng.randint(region_left + 17, region_right - 17)
            regions.extend(((region_left, region_top, split, region_bottom), (split + 1, region_top, region_right, region_bottom)))
        else:
            split = rng.randint(region_top + 17, region_bottom - 17)
            regions.extend(((region_left, region_top, region_right, split), (region_left, split + 1, region_right, region_bottom)))

    for region_left, region_top, region_right, region_bottom in regions:
        region_width = region_right - region_left + 1
        region_height = region_bottom - region_top + 1
        maximum_room_width = region_width - 2
        maximum_room_height = region_height - 2
        room_width = rng.randint(min(maximum_room_width, max(15, maximum_room_width * 3 // 4)), maximum_room_width)
        room_height = rng.randint(min(maximum_room_height, max(15, maximum_room_height * 3 // 4)), maximum_room_height)
        left = rng.randint(region_left + 1, region_right - room_width)
        top = rng.randint(region_top + 1, region_bottom - room_height)
        right = left + room_width - 1
        bottom = top + room_height - 1
        chamber = {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "center_x": (left + right) // 2,
            "center_y": (top + bottom) // 2,
        }
        rooms.append(chamber)
        for tile_x in range(left, right + 1):
            bitmap[top][tile_x] = "#"
            bitmap[bottom][tile_x] = "#"
            door_walls.update(((tile_x, top), (tile_x, bottom)))
        for tile_y in range(top, bottom + 1):
            bitmap[tile_y][left] = "#"
            bitmap[tile_y][right] = "#"
            door_walls.update(((left, tile_y), (right, tile_y)))
        for tile_y in range(top + 1, bottom):
            for tile_x in range(left + 1, right):
                bitmap[tile_y][tile_x] = "."
                room_floor_tiles.append((tile_x, tile_y))

    wall_segment_count = max(1, min(24, width * height // 650))
    for _ in range(wall_segment_count):
        horizontal = rng.choice((True, False))
        segment_length = rng.randint(4, min(12, (width if horizontal else height) // 3))
        if horizontal:
            segment_y = rng.randint(2, height - 3)
            segment_start = rng.randint(2, width - segment_length - 2)
            segment_tiles = [(tile_x, segment_y) for tile_x in range(segment_start, segment_start + segment_length)]
        else:
            segment_x = rng.randint(2, width - 3)
            segment_start = rng.randint(2, height - segment_length - 2)
            segment_tiles = [(segment_x, tile_y) for tile_y in range(segment_start, segment_start + segment_length)]
        if all(bitmap[tile_y][tile_x] == "." for tile_x, tile_y in segment_tiles):
            for tile_x, tile_y in segment_tiles:
                bitmap[tile_y][tile_x] = "#"

    def carve_between(start: Tuple[int, int], end: Tuple[int, int]) -> None:
        _carve_corridor(bitmap, start, end, rng, door_walls, door_tiles, doorways)

    connected_rooms = {0}
    while len(connected_rooms) < len(rooms):
        _, start_index, end_index = min(
            (
                abs(rooms[first]["center_x"] - rooms[second]["center_x"])
                + abs(rooms[first]["center_y"] - rooms[second]["center_y"]),
                first,
                second,
            )
            for first in connected_rooms
            for second in range(len(rooms))
            if second not in connected_rooms
        )
        start_room = rooms[start_index]
        end_room = rooms[end_index]
        carve_between(
            (start_room["center_x"], start_room["center_y"]),
            (end_room["center_x"], end_room["center_y"]),
        )
        connected_rooms.add(end_index)

    for room_index in range(2, len(rooms)):
        if rng.random() < 0.18:
            nearest_index = min(
                range(room_index),
                key=lambda index: abs(rooms[index]["center_x"] - rooms[room_index]["center_x"])
                + abs(rooms[index]["center_y"] - rooms[room_index]["center_y"]),
            )
            source_room = rooms[room_index]
            target_room = rooms[nearest_index]
            carve_between(
                (source_room["center_x"], source_room["center_y"]),
                (target_room["center_x"], target_room["center_y"]),
            )

    _connect_walkable_areas(
        bitmap,
        {(rooms[0]["center_x"], rooms[0]["center_y"])},
        door_walls,
        door_tiles,
        doorways,
        rng,
    )

    stair_positions = set()

    def choose_stair_positions(count: int, from_top: bool) -> List[Tuple[int, int]]:
        maximum_offset = min(11, height - 6)
        candidates = [
            (tile_x, tile_y)
            for chamber in rooms
            for tile_y in range(chamber["top"] + 1, chamber["bottom"])
            for tile_x in range(chamber["left"] + 1, chamber["right"])
            if 5 <= tile_x <= width - 6
            and (5 <= tile_y <= maximum_offset if from_top else 5 <= height - 1 - tile_y <= maximum_offset)
            and (tile_x, tile_y) not in stair_positions
            and all(max(abs(tile_x - door_x), abs(tile_y - door_y)) > 2 for door_x, door_y in door_tiles)
        ]
        if not candidates:
            candidates = [
                (tile_x, tile_y)
                for tile_x, tile_y in room_floor_tiles
                if bitmap[tile_y][tile_x] == "." and (tile_x, tile_y) not in stair_positions
            ]
        positions = []
        for _ in range(min(count, len(candidates))):
            if not stair_positions and not positions:
                selected = rng.choice(candidates)
            else:
                sample_size = min(256, len(candidates))
                sample = rng.sample(candidates, sample_size)
                weights = [
                    max(
                        min(
                            max(abs(tile_x - existing_x), abs(tile_y - existing_y))
                            for existing_x, existing_y in stair_positions | set(positions)
                        ),
                        1,
                    ) ** 2
                    for tile_x, tile_y in sample
                ]
                selected = rng.choices(sample, weights=weights, k=1)[0]
            positions.append(selected)
            candidates.remove(selected)
        stair_positions.update(positions)
        return positions

    room.stair_destinations = {}
    up_destinations = list(room.connected_from)
    if room.floor_index == 1:
        up_destinations.append("Surface")
    up_positions = choose_stair_positions(len(up_destinations), from_top=True)
    for target_id, (stair_x, stair_y) in zip(up_destinations, up_positions):
        nearest_room = min(
            rooms,
            key=lambda candidate: abs(candidate["center_x"] - stair_x)
            + abs(candidate["center_y"] - stair_y),
        )
        carve_between((stair_x, stair_y), (nearest_room["center_x"], nearest_room["center_y"]))
        bitmap[stair_y][stair_x] = "^"
        room.stair_destinations[(stair_x, stair_y)] = target_id

    down_positions = choose_stair_positions(len(room.connected_to), from_top=False)
    for target_id, (stair_x, stair_y) in zip(room.connected_to, down_positions):
        nearest_room = min(
            rooms,
            key=lambda candidate: abs(candidate["center_x"] - stair_x)
            + abs(candidate["center_y"] - stair_y),
        )
        carve_between((stair_x, stair_y), (nearest_room["center_x"], nearest_room["center_y"]))
        bitmap[stair_y][stair_x] = "v"
        room.stair_destinations[(stair_x, stair_y)] = target_id

    _connect_walkable_areas(
        bitmap,
        {next(iter(room.stair_destinations))},
        door_walls,
        door_tiles,
        doorways,
        rng,
    )

    for stair_position, target_id in list(room.stair_destinations.items()):
        stair_x, stair_y = stair_position
        stair_symbol = bitmap[stair_y][stair_x]
        if all(max(abs(stair_x - door_x), abs(stair_y - door_y)) > 2 for door_x, door_y in door_tiles):
            continue
        from_top = stair_symbol == "^"
        maximum_offset = min(11, height - 6)
        candidates = [
            (tile_x, tile_y)
            for chamber in rooms
            for tile_y in range(chamber["top"] + 1, chamber["bottom"])
            for tile_x in range(chamber["left"] + 1, chamber["right"])
            if bitmap[tile_y][tile_x] == "."
            and 5 <= tile_x <= width - 6
            and (5 <= tile_y <= maximum_offset if from_top else 5 <= height - 1 - tile_y <= maximum_offset)
            and all(max(abs(tile_x - door_x), abs(tile_y - door_y)) > 2 for door_x, door_y in door_tiles)
            and all(
                max(abs(tile_x - other_x), abs(tile_y - other_y)) > 2
                for other_x, other_y in room.stair_destinations
                if (other_x, other_y) != stair_position
            )
        ]
        if candidates:
            new_x, new_y = rng.choice(candidates)
            bitmap[stair_y][stair_x] = "."
            bitmap[new_y][new_x] = stair_symbol
            del room.stair_destinations[stair_position]
            room.stair_destinations[(new_x, new_y)] = target_id

    _connect_walkable_areas(
        bitmap,
        {next(iter(room.stair_destinations))},
        door_walls,
        door_tiles,
        doorways,
        rng,
    )

    room.gates = _place_gates(bitmap, room_floor_tiles, doorways, room.stair_destinations, rng)

    def place_tile(tile: str, count: int) -> None:
        candidates = [
            (tile_x, tile_y)
            for tile_x, tile_y in room_floor_tiles
            if bitmap[tile_y][tile_x] == "."
        ]
        for _ in range(min(count, len(candidates))):
            tile_x, tile_y = rng.choice(candidates)
            bitmap[tile_y][tile_x] = tile
            candidates.remove((tile_x, tile_y))

    area_scale = min(4, 1 + width * height // 2200)
    place_tile("T", rng.randint(1, area_scale))
    chest_count = rng.choices((0, 1, 2), weights=(6, 3, 1) if room.is_dead_end else (7, 3, 1))[0]
    for _ in range(chest_count):
        place_tile("C", 1)

    lore_count = 1 if room.is_dead_end or rng.random() < 0.3 else 0
    place_tile("L", lore_count)

    return ["".join(row) for row in bitmap]


def _place_gates(
    bitmap: List[List[str]],
    room_floor_tiles: List[Tuple[int, int]],
    doorways: List[frozenset[Tuple[int, int]]],
    stair_destinations: Dict[Tuple[int, int], str],
    rng: random.Random,
) -> Dict[str, Dict[str, object]]:
    stair_entries = [position for position in stair_destinations if bitmap[position[1]][position[0]] == "^"]
    if not stair_entries:
        return {}

    start = stair_entries[0]
    height = len(bitmap)
    width = len(bitmap[0])

    def reachable(blocked: set[Tuple[int, int]]) -> set[Tuple[int, int]]:
        visited = {start}
        queue = deque([start])
        while queue:
            tile_x, tile_y = queue.popleft()
            for neighbor in ((tile_x - 1, tile_y), (tile_x + 1, tile_y), (tile_x, tile_y - 1), (tile_x, tile_y + 1)):
                neighbor_x, neighbor_y = neighbor
                if (
                    0 < neighbor_x < width - 1
                    and 0 < neighbor_y < height - 1
                    and neighbor not in visited
                    and neighbor not in blocked
                    and bitmap[neighbor_y][neighbor_x] not in ("#", "D")
                ):
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    closed_tiles: set[Tuple[int, int]] = set()
    gates: Dict[str, Dict[str, object]] = {}
    gate_sections: Dict[str, set[Tuple[int, int]]] = {}
    used_doorways = set()
    all_doorway_tiles = set().union(*doorways) if doorways else set()
    walkable_count = sum(tile != "#" for row in bitmap for tile in row)
    minimum_locked_area = max(12, int(walkable_count * 0.025))
    target_gate_count = rng.choices((1, 2, 3), weights=(6, 3, 1))[0]
    has_down_stairs = any(bitmap[y][x] == "v" for x, y in stair_destinations)
    room_floor_set = set(room_floor_tiles)

    for gate_index in range(target_gate_count):
        current_reachable = reachable(closed_tiles)
        candidates = []
        for doorway in doorways:
            if doorway in used_doorways or len(doorway) < 5 or doorway & closed_tiles:
                continue
            doorway_tiles = {point for point in doorway if bitmap[point[1]][point[0]] not in ("#", "D")}
            if len(doorway_tiles) < 5:
                continue
            after_closing = reachable(closed_tiles | doorway_tiles)
            locked_section = current_reachable - after_closing
            if len(locked_section) < minimum_locked_area:
                continue
            if any(bitmap[tile_y][tile_x] == "V" for tile_x, tile_y in locked_section):
                continue
            if any(bitmap[tile_y][tile_x] == "^" for tile_x, tile_y in locked_section):
                continue
            if has_down_stairs:
                blocked_door_tiles = all_doorway_tiles | doorway_tiles
                has_stair_spot = any(
                    bitmap[tile_y][tile_x] == "."
                    and 5 <= tile_x <= width - 6
                    and 5 <= height - 1 - tile_y <= 11
                    and all(
                        max(abs(tile_x - door_x), abs(tile_y - door_y)) > 2
                        for door_x, door_y in blocked_door_tiles
                    )
                    for tile_x, tile_y in room_floor_set & locked_section
                )
                has_existing_stair = any(
                    bitmap[tile_y][tile_x] == "v"
                    and 5 <= tile_x <= width - 6
                    and 5 <= height - 1 - tile_y <= 11
                    and all(
                        max(abs(tile_x - door_x), abs(tile_y - door_y)) > 2
                        for door_x, door_y in blocked_door_tiles
                    )
                    for tile_x, tile_y in locked_section
                )
                if not has_stair_spot and not has_existing_stair:
                    continue

            lever_candidates = [
                point for point in room_floor_tiles
                if point in after_closing and bitmap[point[1]][point[0]] == "."
            ]
            if not lever_candidates:
                continue

            door_position = min(
                doorway_tiles,
                key=lambda point: sum(
                    max(abs(point[0] - other_x), abs(point[1] - other_y))
                    for other_x, other_y in doorway_tiles
                ),
            )
            lever_candidates.sort(
                key=lambda point: min(
                    abs(point[0] - door_x) + abs(point[1] - door_y)
                    for door_x, door_y in doorway_tiles
                )
            )
            candidates.append((len(locked_section), doorway, doorway_tiles, door_position, locked_section, lever_candidates[:12]))

        if not candidates:
            break

        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        preferred = candidates[:min(3, len(candidates))]
        weights = [candidate[0] for candidate in preferred]
        locked_count, doorway, doorway_tiles, door_position, locked_section, lever_candidates = rng.choices(
            preferred, weights=weights, k=1
        )[0]
        lever_position = rng.choice(lever_candidates)
        gate_id = f"G{gate_index + 1}"

        for tile_x, tile_y in doorway_tiles:
            bitmap[tile_y][tile_x] = "#"
        bitmap[door_position[1]][door_position[0]] = "D"
        bitmap[lever_position[1]][lever_position[0]] = "V"
        closed_tiles.update(doorway_tiles)
        used_doorways.add(doorway)
        gates[gate_id] = {
            "tiles": sorted(doorway_tiles),
            "door": door_position,
            "lever": lever_position,
            "locked_tiles": locked_count,
        }
        gate_sections[gate_id] = set(locked_section)

    down_stairs = [
        (position, destination)
        for position, destination in stair_destinations.items()
        if bitmap[position[1]][position[0]] == "v"
    ]
    if gates and down_stairs:
        accessible_tiles = reachable(closed_tiles)

        def valid_stair_tiles(region: set[Tuple[int, int]]) -> List[Tuple[int, int]]:
            return [
                position for position in room_floor_tiles
                if position in region
                and bitmap[position[1]][position[0]] == "."
                and 5 <= position[0] <= width - 6
                and 5 <= height - 1 - position[1] <= 11
                and all(
                    max(abs(position[0] - door_x), abs(position[1] - door_y)) > 2
                    for door_x, door_y in all_doorway_tiles
                )
            ]

        gate_options = []
        for gate_id, section in gate_sections.items():
            locked_region = section - accessible_tiles
            existing_stairs = [
                position for position, _ in down_stairs
                if position in locked_region
                and 5 <= position[0] <= width - 6
                and 5 <= height - 1 - position[1] <= 11
                and all(
                    max(abs(position[0] - door_x), abs(position[1] - door_y)) > 2
                    for door_x, door_y in all_doorway_tiles
                )
            ]
            locked_stair_spots = valid_stair_tiles(locked_region)
            if existing_stairs or locked_stair_spots:
                gate_options.append((len(existing_stairs), len(locked_stair_spots), gate_id, locked_region, existing_stairs, locked_stair_spots))

        if gate_options:
            gate_options.sort(key=lambda option: (option[0] == 1, option[0] > 0, option[1], len(option[3])), reverse=True)
            _, _, selected_gate, selected_region, existing_stairs, locked_stair_spots = gate_options[0]
            if existing_stairs:
                selected_stair = existing_stairs[0]
            else:
                selected_stair = rng.choice(locked_stair_spots)
                source_stair, destination = down_stairs[0]
                bitmap[source_stair[1]][source_stair[0]] = "."
                stair_destinations.pop(source_stair)
                stair_destinations[selected_stair] = destination
                bitmap[selected_stair[1]][selected_stair[0]] = "v"

            for position, destination in list(stair_destinations.items()):
                if bitmap[position[1]][position[0]] != "v" or position == selected_stair:
                    continue
                if position in accessible_tiles:
                    continue
                replacement_tiles = valid_stair_tiles(accessible_tiles)
                replacement_tiles = [
                    replacement for replacement in replacement_tiles
                    if replacement not in stair_destinations
                    and all(max(abs(replacement[0] - other[0]), abs(replacement[1] - other[1])) > 2
                            for other in stair_destinations if other != position)
                ]
                if replacement_tiles:
                    replacement = rng.choice(replacement_tiles)
                    bitmap[position[1]][position[0]] = "."
                    stair_destinations.pop(position)
                    stair_destinations[replacement] = destination
                    bitmap[replacement[1]][replacement[0]] = "v"

            gates[selected_gate]["down_stair"] = selected_stair

    return gates


def _carve_corridor(
    bitmap: List[List[str]],
    start: Tuple[int, int],
    end: Tuple[int, int],
    rng: random.Random,
    door_walls: set[Tuple[int, int]],
    door_tiles: set[Tuple[int, int]],
    doorways: List[frozenset[Tuple[int, int]]],
) -> None:
    start_x, start_y = start
    end_x, end_y = end
    bend = (end_x, start_y) if rng.random() < 0.5 else (start_x, end_y)
    waypoints = (start, bend, end)
    height = len(bitmap)
    width = len(bitmap[0])

    for segment_index in range(2):
        segment_start = waypoints[segment_index]
        segment_end = waypoints[segment_index + 1]
        horizontal = segment_start[1] == segment_end[1]
        corridor_width = rng.randint(5, 15)
        if horizontal:
            step = 1 if segment_end[0] >= segment_start[0] else -1
            centerline = ((tile_x, segment_start[1]) for tile_x in range(segment_start[0], segment_end[0] + step, step))
            cross_size = height
        else:
            step = 1 if segment_end[1] >= segment_start[1] else -1
            centerline = ((segment_start[0], tile_y) for tile_y in range(segment_start[1], segment_end[1] + step, step))
            cross_size = width

        for tile_x, tile_y in centerline:
            center_tile = (tile_x, tile_y)
            if bitmap[tile_y][tile_x] == "#" and center_tile in door_walls:
                opening_width = min(corridor_width, sum(
                    1 for offset in range(-corridor_width, corridor_width + 1)
                    if ((tile_x, tile_y + offset) if horizontal else (tile_x + offset, tile_y)) in door_walls
                ))
                opening_width = max(5, opening_width)
                negative_offset = opening_width // 2
                opening = [
                    (tile_x, tile_y + offset) if horizontal else (tile_x + offset, tile_y)
                    for offset in range(-negative_offset, opening_width - negative_offset)
                ]
                opening = [point for point in opening if point in door_walls]
                for opening_x, opening_y in opening:
                    bitmap[opening_y][opening_x] = "."
                    door_tiles.add((opening_x, opening_y))
                if opening:
                    doorways.append(frozenset(opening))
            if bitmap[tile_y][tile_x] == "#" and center_tile not in door_walls:
                bitmap[tile_y][tile_x] = "."

            cross_start = max(1, min(cross_size - 1 - corridor_width, (tile_y if horizontal else tile_x) - corridor_width // 2))
            cross_end = min(cross_size - 1, cross_start + corridor_width)
            for cross_position in range(cross_start, cross_end):
                cross_tile = (tile_x, cross_position) if horizontal else (cross_position, tile_y)
                cross_x, cross_y = cross_tile
                if bitmap[cross_y][cross_x] == "#" and cross_tile not in door_walls:
                    bitmap[cross_y][cross_x] = "."


    def _place_gates(
        bitmap: List[List[str]],
        room_floor_tiles: List[Tuple[int, int]],
        doorways: List[frozenset[Tuple[int, int]]],
        stair_destinations: Dict[Tuple[int, int], str],
        rng: random.Random,
    ) -> Dict[str, Dict[str, object]]:
        stair_entries = [
            position for position in stair_destinations
            if bitmap[position[1]][position[0]] == "^"
        ]
        if not stair_entries:
            return {}

        start = stair_entries[0]
        height = len(bitmap)
        width = len(bitmap[0])

        def reachable(blocked: set[Tuple[int, int]]) -> set[Tuple[int, int]]:
            visited = {start}
            queue = deque([start])
            while queue:
                tile_x, tile_y = queue.popleft()
                for neighbor in ((tile_x - 1, tile_y), (tile_x + 1, tile_y), (tile_x, tile_y - 1), (tile_x, tile_y + 1)):
                    neighbor_x, neighbor_y = neighbor
                    if (
                        0 < neighbor_x < width - 1
                        and 0 < neighbor_y < height - 1
                        and neighbor not in visited
                        and neighbor not in blocked
                        and bitmap[neighbor_y][neighbor_x] not in ("#", "D")
                    ):
                        visited.add(neighbor)
                        queue.append(neighbor)
            return visited

        closed_tiles: set[Tuple[int, int]] = set()
        gates: Dict[str, Dict[str, object]] = {}
        used_doorways = set()
        walkable_count = sum(tile != "#" for row in bitmap for tile in row)
        minimum_locked_area = max(12, int(walkable_count * 0.025))
        target_gate_count = rng.choices((1, 2, 3), weights=(6, 3, 1))[0]

        for gate_index in range(target_gate_count):
            current_reachable = reachable(closed_tiles)
            candidates = []
            for doorway in doorways:
                if doorway in used_doorways or len(doorway) < 5 or doorway & closed_tiles:
                    continue
                doorway_tiles = {position for position in doorway if bitmap[position[1]][position[0]] not in ("#", "D")}
                if len(doorway_tiles) < 5:
                    continue
                after_closing = reachable(closed_tiles | doorway_tiles)
                locked_section = current_reachable - after_closing
                if len(locked_section) < minimum_locked_area:
                    continue

                lever_candidates = [
                    position for position in room_floor_tiles
                    if position in after_closing and bitmap[position[1]][position[0]] == "."
                ]
                if not lever_candidates:
                    continue

                door_center = min(
                    doorway_tiles,
                    key=lambda position: sum(
                        max(abs(position[0] - other_x), abs(position[1] - other_y))
                        for other_x, other_y in doorway_tiles
                    ),
                )
                lever_candidates.sort(
                    key=lambda position: min(
                        abs(position[0] - door_x) + abs(position[1] - door_y)
                        for door_x, door_y in doorway_tiles
                    )
                )
                best_levers = lever_candidates[:min(12, len(lever_candidates))]
                candidates.append((len(locked_section), doorway, doorway_tiles, door_center, after_closing, best_levers))

            if not candidates:
                break

            candidates.sort(key=lambda candidate: candidate[0], reverse=True)
            preferred = candidates[:min(3, len(candidates))]
            weights = [candidate[0] for candidate in preferred]
            locked_count, doorway, doorway_tiles, door_position, _, lever_candidates = rng.choices(
                preferred, weights=weights, k=1
            )[0]
            lever_position = rng.choice(lever_candidates)
            gate_id = f"G{gate_index + 1}"

            for tile_x, tile_y in doorway_tiles:
                bitmap[tile_y][tile_x] = "#"
            bitmap[door_position[1]][door_position[0]] = "D"
            bitmap[lever_position[1]][lever_position[0]] = "V"
            closed_tiles.update(doorway_tiles)
            used_doorways.add(doorway)
            gates[gate_id] = {
                "tiles": sorted(doorway_tiles),
                "door": door_position,
                "lever": lever_position,
                "locked_tiles": locked_count,
            }

        return gates


def _connect_walkable_areas(
    bitmap: List[List[str]],
    stair_tiles: set[Tuple[int, int]],
    door_walls: set[Tuple[int, int]],
    door_tiles: set[Tuple[int, int]],
    doorways: List[frozenset[Tuple[int, int]]],
    rng: random.Random,
) -> None:
    height = len(bitmap)
    width = len(bitmap[0])
    connected = set(stair_tiles)
    queue = deque(stair_tiles)
    while queue:
        tile_x, tile_y = queue.popleft()
        for neighbor in ((tile_x - 1, tile_y), (tile_x + 1, tile_y), (tile_x, tile_y - 1), (tile_x, tile_y + 1)):
            neighbor_x, neighbor_y = neighbor
            if (
                0 < neighbor_x < width - 1
                and 0 < neighbor_y < height - 1
                and bitmap[neighbor_y][neighbor_x] != "#"
                and neighbor not in connected
            ):
                connected.add(neighbor)
                queue.append(neighbor)

    disconnected = [
        (tile_x, tile_y)
        for tile_y in range(1, height - 1)
        for tile_x in range(1, width - 1)
        if bitmap[tile_y][tile_x] != "#" and (tile_x, tile_y) not in connected
    ]
    while disconnected:
        target = disconnected.pop()
        source = min(connected, key=lambda tile: abs(tile[0] - target[0]) + abs(tile[1] - target[1]))
        _carve_corridor(bitmap, source, target, rng, door_walls, door_tiles, doorways)
        connected.add(target)
        queue.append(target)
        while queue:
            tile_x, tile_y = queue.popleft()
            for neighbor in ((tile_x - 1, tile_y), (tile_x + 1, tile_y), (tile_x, tile_y - 1), (tile_x, tile_y + 1)):
                neighbor_x, neighbor_y = neighbor
                if (
                    0 < neighbor_x < width - 1
                    and 0 < neighbor_y < height - 1
                    and bitmap[neighbor_y][neighbor_x] != "#"
                    and neighbor not in connected
                ):
                    connected.add(neighbor)
                    queue.append(neighbor)
        disconnected = [tile for tile in disconnected if tile not in connected]