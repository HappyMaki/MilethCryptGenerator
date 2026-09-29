import random
from collections import deque
from math import ceil
from typing import List, Dict, Optional, Tuple


BITMAP_LEGEND = {
    ".": {"name": "Floor", "color": "#454744"},
    "#": {"name": "Wall", "color": "#242b2a"},
    "C": {"name": "Chest", "color": "#b0974f"},
    "G": {"name": "Gathering Node", "color": "#6f9b65"},
    "M": {"name": "Monster Spawn Point", "color": "#b34a3c"},
    "^": {"name": "Stairs Up", "color": "#32f66b"},
    "v": {"name": "Stairs Down", "color": "#ff2b4f"},
    "L": {"name": "Lore Event", "color": "#647b8a"},
    "D": {"name": "Locked Gate", "color": "#a34e43"},
    "V": {"name": "Gate Lever", "color": "#c49a52"},
}
MIN_SPAWN_ROOM_TILES = 100
# Levers are wall mounted next to the gate they open, never scattered across the room.
LEVER_MIN_DOOR_DISTANCE = 2
LEVER_MAX_DOOR_DISTANCE = 4
# A share of stairs on deeper floors get walled into a locked closet of their own.
STAIR_CLOSET_CHANCE = 0.15
STAIR_CLOSET_MIN_FLOOR = 3


class RoomNode:
    """Represents an individual room or node in the dungeon network."""
    def __init__(self, room_id: str, floor_index: int, grid_x: int, is_main_path: bool = False):
        self.room_id = room_id
        self.floor_index = floor_index
        self.grid_x = grid_x
        self.is_main_path = is_main_path
        self.is_dead_end = False
        self.is_resting_area = False
        self.is_lore_room = False
        self.connected_to: List[str] = []    # Stair connections leading Down
        self.connected_from: List[str] = []  # Stair connections leading Up
        self.bitmap: List[str] = []
        self.stair_destinations: Dict[Tuple[int, int], str] = {}
        self.gathering_nodes: Dict[Tuple[int, int], Dict[str, object]] = {}
        self.monster_spawn_points: List[Tuple[int, int]] = []
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
    seed: Optional[int] = None,
    spawn_point_ratio: float = 0.0045,
) -> DungeonPath:
    """
    Generates a procedural dungeon topology with a guaranteed critical path,
    optional branching paths, restricted deep dead ends, and orphan pruning.
    Spawn point ratio is the desired number of wall markers per walkable tile.
    """
    if not 0 <= spawn_point_ratio <= 1:
        raise ValueError("spawn_point_ratio must be between 0 and 1")

    dungeon = DungeonPath(name)
    rng = random.Random(seed)

    # Floor depth threshold where dead ends start appearing (e.g., floor >= 4 on a 10-floor dungeon)
    min_dead_end_floor = int(num_floors * (1.0 - dead_end_depth_pct)) + 1
    interior_floors = list(range(2, num_floors))
    multi_room_floors = {
        min(interior_floors, key=lambda floor: abs(floor / num_floors - target_fraction))
        for target_fraction in (0.35, 0.65)
    } if interior_floors else set()
    if len(multi_room_floors) < min(2, len(interior_floors)):
        multi_room_floors.update(floor for floor in interior_floors if floor not in multi_room_floors)
        multi_room_floors = set(sorted(multi_room_floors)[:min(2, len(interior_floors))])
    lore_floor = max(2, min(num_floors - 5, int(num_floors * 0.3))) if num_floors >= 7 else None
    if lore_floor is not None:
        multi_room_floors.add(lore_floor)

    # 1. Instantiate Rooms per floor
    for floor in range(1, num_floors + 1):
        dungeon.floors[floor] = []
        room_count = (
            1 if (floor == 1 or floor == num_floors)
            else 4 if floor == lore_floor
            else rng.randint(3, 4) if floor in multi_room_floors
            else rng.randint(2, 4)
        )
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
                if floor + 1 in multi_room_floors:
                    for target in lower_rooms:
                        if target.room_id not in room.connected_to:
                            room.connected_to.append(target.room_id)
                else:
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
    reachable_ids = {room_id_map[room_id] for room_id in reachable_ids}

    rest_floors = [floor for floor in dungeon.floors if 0.7 <= floor / num_floors <= 0.9]
    if not rest_floors:
        rest_floors = list(dungeon.floors)
    rest_floor = min(rest_floors, key=lambda floor: abs(floor / num_floors - 0.8))
    rest_room_id = dungeon.critical_path[rest_floor - 1]
    next(room for room in dungeon.floors[rest_floor] if room.room_id == rest_room_id).is_resting_area = True

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
            room.bitmap = _generate_room_bitmap(room, rng, spawn_point_ratio)

    if lore_floor is not None:
        _add_lore_dead_end_route(dungeon, lore_floor, rng)

    return dungeon


def _generate_secret_shaft_bitmap(
    room: RoomNode,
    down_target: Optional[str],
    up_target: Optional[str],
    rng: random.Random,
) -> List[str]:
    """Builds the small 15x15 chamber used for one step of the lore secret shaft."""
    width = height = 15
    bitmap = [["#" for _ in range(width)] for _ in range(height)]
    for tile_y in range(1, height - 1):
        for tile_x in range(1, width - 1):
            bitmap[tile_y][tile_x] = "."

    room.stair_destinations = {}
    if down_target is not None:
        position = (rng.randint(4, 10), height - 2)
        bitmap[position[1]][position[0]] = "v"
        room.stair_destinations[position] = down_target
        room.connected_to.append(down_target)
    if up_target is not None:
        position = (rng.randint(4, 10), 1)
        bitmap[position[1]][position[0]] = "^"
        room.stair_destinations[position] = up_target
        room.connected_from.append(up_target)

    room.gathering_nodes = {}
    room.monster_spawn_points = []
    return ["".join(row) for row in bitmap]


def _seal_stair_closet(
    room: RoomNode,
    stair_position: Tuple[int, int],
    gate_id: str,
    rng: random.Random,
) -> bool:
    """
    Walls an existing stair into its own 3x3 closet sealed by a locked gate.

    The stair stays reachable only after the player works the gate open. Every tile
    the closet consumes must be bare floor and clear of anything already placed, so
    the room's stairs, gates, chests and nodes are never overwritten. Returns False
    when the stair cannot be boxed in without disturbing the room.
    """
    height = len(room.bitmap)
    width = len(room.bitmap[0])
    center_x, center_y = stair_position

    reserved = set(room.stair_destinations)
    for gate in room.gates.values():
        reserved.update(gate["tiles"])
        reserved.add(gate["door"])
        reserved.add(gate["lever"])
    reserved.discard(stair_position)

    def put(tile_x: int, tile_y: int, symbol: str) -> None:
        # Rows are mutable lists while a room is still being generated and plain
        # strings once the room is finished, so accept either representation.
        row = room.bitmap[tile_y]
        if isinstance(row, str):
            room.bitmap[tile_y] = row[:tile_x] + symbol + row[tile_x + 1:]
        else:
            row[tile_x] = symbol

    for offset_y in range(-1, 2):
        for offset_x in range(-1, 2):
            tile_x, tile_y = center_x + offset_x, center_y + offset_y
            if not (0 <= tile_x < width and 0 <= tile_y < height):
                return False
            if (tile_x, tile_y) == stair_position:
                continue
            if room.bitmap[tile_y][tile_x] != ".":
                return False
    for offset_y in range(-2, 3):
        for offset_x in range(-2, 3):
            if abs(offset_x) != 2 and abs(offset_y) != 2:
                continue
            tile_x, tile_y = center_x + offset_x, center_y + offset_y
            if not (0 <= tile_x < width and 0 <= tile_y < height):
                return False
            if room.bitmap[tile_y][tile_x] != ".":
                return False
            if any(
                max(abs(tile_x - other[0]), abs(tile_y - other[1])) <= 2
                for other in reserved
            ):
                return False

    def outside_floor_count(side: str) -> int:
        offsets = {
            "top": [(center_x + step, center_y - 3) for step in (-1, 0, 1)],
            "bottom": [(center_x + step, center_y + 3) for step in (-1, 0, 1)],
            "left": [(center_x - 3, center_y + step) for step in (-1, 0, 1)],
            "right": [(center_x + 3, center_y + step) for step in (-1, 0, 1)],
        }[side]
        return sum(
            1
            for tile_x, tile_y in offsets
            if 0 <= tile_x < width and 0 <= tile_y < height and room.bitmap[tile_y][tile_x] == "."
        )

    def gate_tiles_for(side: str) -> List[Tuple[int, int]]:
        return {
            "top": [(center_x + step, center_y - 2) for step in (-1, 0, 1)],
            "bottom": [(center_x + step, center_y + 2) for step in (-1, 0, 1)],
            "left": [(center_x - 2, center_y + step) for step in (-1, 0, 1)],
            "right": [(center_x + 2, center_y + step) for step in (-1, 0, 1)],
        }[side]

    closet_tiles = {
        (center_x + offset_x, center_y + offset_y)
        for offset_y in range(-1, 2)
        for offset_x in range(-1, 2)
    }
    for offset_y in range(-2, 3):
        for offset_x in range(-2, 3):
            if abs(offset_x) == 2 or abs(offset_y) == 2:
                put(center_x + offset_x, center_y + offset_y, "#")

    outside_floor = [
        (tile_x, tile_y)
        for tile_y in range(height)
        for tile_x in range(width)
        if room.bitmap[tile_y][tile_x] == "."
        and (tile_x, tile_y) not in closet_tiles
    ]

    for side in sorted(("top", "bottom", "left", "right"), key=lambda name: -outside_floor_count(name)):
        gate_tiles = gate_tiles_for(side)
        door = gate_tiles[1]
        for tile_x, tile_y in gate_tiles:
            put(tile_x, tile_y, "#")
        put(*door, "D")
        lever = _select_lever_tile(room.bitmap, outside_floor, door)
        if lever is not None:
            put(*lever, "V")
            room.gates[gate_id] = {
                "tiles": sorted(gate_tiles),
                "door": door,
                "lever": lever,
                "locked_tiles": len(closet_tiles),
            }
            return True
        put(*door, "#")

    for offset_y in range(-2, 3):
        for offset_x in range(-2, 3):
            if abs(offset_x) == 2 or abs(offset_y) == 2:
                put(center_x + offset_x, center_y + offset_y, ".")
    return False


def _seal_random_stair_closets(room: RoomNode, rng: random.Random) -> None:
    """
    Rolls a locked closet around a small share of a deep room's stairs.

    Only rooms below the shallow floors qualify, so the early game stays open and the
    gated stair chambers read as a deeper-dungeon flourish.
    """
    if room.floor_index <= STAIR_CLOSET_MIN_FLOOR:
        return
    # Rest areas are hand drawn string bitmaps, so only grid rooms qualify here.
    if not room.bitmap or not isinstance(room.bitmap[0], list):
        return
    for stair_position in list(room.stair_destinations):
        if rng.random() >= STAIR_CLOSET_CHANCE:
            continue
        if room.bitmap[stair_position[1]][stair_position[0]] not in ("^", "v"):
            continue
        _seal_stair_closet(room, stair_position, f"G{len(room.gates) + 1}", rng)


def _place_secret_stair(
    room: RoomNode,
    target_id: str,
    rng: random.Random,
) -> Optional[Tuple[int, int]]:
    """
    Boxes the secret stair into its own walled closet and seals it behind a gate.

    A 3x3 chamber is walled off from the room with a locked gate and a wall mounted
    lever, so the stair that drops into the lore shaft is only reachable after the
    player works the gate open. The whole footprint must be bare floor, so nothing
    already placed in the room gets overwritten.
    """
    height = len(room.bitmap)
    width = len(room.bitmap[0])

    reserved = set(room.stair_destinations)
    for gate in room.gates.values():
        reserved.update(gate["tiles"])
        reserved.add(gate["door"])
        reserved.add(gate["lever"])

    def footprint_clear(origin: Tuple[int, int]) -> bool:
        origin_x, origin_y = origin
        return all(
            0 <= origin_x + offset_x < width
            and 0 <= origin_y + offset_y < height
            and room.bitmap[origin_y + offset_y][origin_x + offset_x] == "."
            for offset_y in range(-2, 3)
            for offset_x in range(-2, 3)
        )

    def spaced_clear(origin: Tuple[int, int]) -> bool:
        return all(
            max(abs(origin[0] - other[0]), abs(origin[1] - other[1])) > 3
            for other in reserved
        )

    origins = [
        (tile_x, tile_y)
        for tile_y in range(2, height - 2)
        for tile_x in range(2, width - 2)
        if footprint_clear((tile_x, tile_y)) and spaced_clear((tile_x, tile_y))
    ]
    if not origins:
        return None
    center_x, center_y = rng.choice(origins)

    def put(tile_x: int, tile_y: int, symbol: str) -> None:
        row = list(room.bitmap[tile_y])
        row[tile_x] = symbol
        room.bitmap[tile_y] = "".join(row)

    closet_tiles = {
        (center_x + offset_x, center_y + offset_y)
        for offset_y in range(-1, 2)
        for offset_x in range(-1, 2)
    }
    stair_position = (center_x, center_y)
    for offset_y in range(-1, 2):
        for offset_x in range(-1, 2):
            row = list(room.bitmap[center_y + offset_y])
            row[center_x + offset_x] = "."
            room.bitmap[center_y + offset_y] = "".join(row)
    put(*stair_position, "^")
    room.stair_destinations[stair_position] = target_id
    room.connected_from.append(target_id)

    if not _seal_stair_closet(room, stair_position, f"G{len(room.gates) + 1}", rng):
        return None
    return stair_position


def _add_lore_dead_end_route(dungeon: DungeonPath, floor: int, rng: random.Random) -> None:
    """
    Turns a side room on `floor` into a secret lore dead end reached by climbing a
    shaft of small floors.

    The lore room keeps a single stair leading down onto the first shaft floor, and
    the shaft climbs back up to it one floor at a time. Every step is a small 15x15
    room appended to its own floor, so the player walks across each floor and takes
    a single stair per level instead of riding one stair that skips five floors.
    """
    floor_rooms = dungeon.floors[floor]
    lore_room = next(
        room
        for index, room in enumerate(floor_rooms)
        if 0 < index < len(floor_rooms) - 1 and not room.is_main_path
    )
    lore_room_id = lore_room.room_id
    shaft_depth = min(5, len(dungeon.floors) - floor)
    shaft_floors = list(range(floor + 1, floor + 1 + shaft_depth))

    def set_tile(room: RoomNode, position: Tuple[int, int], tile: str) -> None:
        tile_x, tile_y = position
        row = list(room.bitmap[tile_y])
        row[tile_x] = tile
        room.bitmap[tile_y] = "".join(row)

    def accessible_floor_tile(room: RoomNode, starts: List[Tuple[int, int]]) -> Tuple[int, int]:
        height = len(room.bitmap)
        width = len(room.bitmap[0])
        visited = set(starts)
        queue = deque(starts)
        while queue:
            tile_x, tile_y = queue.popleft()
            for neighbor_x, neighbor_y in (
                (tile_x - 1, tile_y),
                (tile_x + 1, tile_y),
                (tile_x, tile_y - 1),
                (tile_x, tile_y + 1),
            ):
                neighbor = (neighbor_x, neighbor_y)
                if (
                    0 < neighbor_x < width - 1
                    and 0 < neighbor_y < height - 1
                    and neighbor not in visited
                    and room.bitmap[neighbor_y][neighbor_x] not in ("#", "D")
                ):
                    visited.add(neighbor)
                    queue.append(neighbor)
        candidates = [
            (tile_x, tile_y)
            for tile_x, tile_y in visited
            if room.bitmap[tile_y][tile_x] == "."
        ]
        if not candidates:
            candidates = [
                (tile_x, tile_y)
                for tile_y, row in enumerate(room.bitmap)
                for tile_x, tile in enumerate(row)
                if tile == "."
            ]
        if not candidates:
            raise ValueError(f"No available stair tile in room {room.room_id}")
        return rng.choice(candidates)

    incoming = [
        (room, position)
        for room in dungeon.floors[floor - 1]
        for position, destination in room.stair_destinations.items()
        if destination == lore_room_id and room.bitmap[position[1]][position[0]] == "v"
    ]
    lore_entry_positions = [
        position
        for position in lore_room.stair_destinations
        if lore_room.bitmap[position[1]][position[0]] == "^"
    ]
    if not lore_entry_positions:
        raise ValueError(f"Lore room {lore_room_id} has no existing upper stair to replace")

    lore_down_position = accessible_floor_tile(lore_room, lore_entry_positions)

    for upper_room, position in incoming:
        upper_room.connected_to.remove(lore_room_id)
        del upper_room.stair_destinations[position]
        set_tile(upper_room, position, ".")
    for position, destination in list(lore_room.stair_destinations.items()):
        if lore_room.bitmap[position[1]][position[0]] == "^":
            del lore_room.stair_destinations[position]
            set_tile(lore_room, position, ".")

    for old_lower_id in list(lore_room.connected_to):
        old_lower_room = next(
            room
            for level in shaft_floors
            for room in dungeon.floors[level]
            if room.room_id == old_lower_id
        )
        old_lower_room.connected_from.remove(lore_room_id)
        for position, destination in list(old_lower_room.stair_destinations.items()):
            if destination == lore_room_id and old_lower_room.bitmap[position[1]][position[0]] == "^":
                del old_lower_room.stair_destinations[position]
                set_tile(old_lower_room, position, ".")
    for position, destination in list(lore_room.stair_destinations.items()):
        if lore_room.bitmap[position[1]][position[0]] == "v":
            del lore_room.stair_destinations[position]
            set_tile(lore_room, position, ".")

    # The bottom of the shaft has to open back into the dungeon, otherwise the lore
    # room and the whole climb are unreachable. Link it to a side room one floor
    # below so the player finds the shaft at its foot and climbs up to the secret.
    bottom_floor = shaft_floors[-1]
    host_room = next(
        (room for room in dungeon.floors.get(bottom_floor + 1, ()) if not room.is_main_path),
        None,
    )
    if host_room is None:
        host_room = next(iter(dungeon.floors.get(bottom_floor + 1, ())), None)
    if host_room is None:
        host_room = next(iter(dungeon.floors.get(bottom_floor - 1, ())), None)

    # Build the shaft top-down so every step knows the room above and below it.
    # Each room is numbered on the floor it actually sits on, so the chain reads
    # 9-4S, 10-1S, 11-1S ... as it descends instead of repeating one floor's index.
    shaft_ids: List[str] = []
    for shaft_floor in shaft_floors:
        existing = {room.room_id for room in dungeon.floors[shaft_floor]}
        next_index = 1
        while f"{shaft_floor}-{next_index}" in existing:
            next_index += 1
        shaft_ids.append(f"{shaft_floor}-{next_index}S")

    shaft_rooms: List[RoomNode] = []
    for index, shaft_floor in enumerate(shaft_floors):
        down_target = shaft_ids[index + 1] if index + 1 < len(shaft_floors) else (host_room.room_id if host_room else None)
        up_target = lore_room_id if index == 0 else shaft_ids[index - 1]
        shaft_room = RoomNode(
            room_id=shaft_ids[index],
            floor_index=shaft_floor,
            grid_x=len(dungeon.floors[shaft_floor]),
            is_main_path=False,
        )
        shaft_room.bitmap = _generate_secret_shaft_bitmap(shaft_room, down_target, up_target, rng)
        dungeon.floors[shaft_floor].append(shaft_room)
        shaft_rooms.append(shaft_room)

    if host_room is not None and _place_secret_stair(host_room, shaft_ids[-1], rng) is None:
        raise ValueError(f"Host room {host_room.room_id} has no clear tile for the secret stair")

    first_shaft_room = shaft_rooms[0]
    lore_room.connected_from.clear()
    lore_room.connected_to = [first_shaft_room.room_id]
    first_shaft_room.connected_from.append(lore_room_id)
    lore_room.stair_destinations[lore_down_position] = first_shaft_room.room_id
    set_tile(lore_room, lore_down_position, "v")
    lore_room.is_lore_room = True
    lore_room.is_dead_end = True

    if not any(tile == "L" for row in lore_room.bitmap for tile in row):
        lore_tile = accessible_floor_tile(lore_room, [lore_down_position])
        set_tile(lore_room, lore_tile, "L")


def _select_lever_tile(
    bitmap: List[List[str]],
    floor_tiles: List[Tuple[int, int]],
    door_position: Tuple[int, int],
    solid_wall_tiles: Optional[set[Tuple[int, int]]] = None,
) -> Optional[Tuple[int, int]]:
    """
    Picks the wall tile a gate lever is mounted on.

    Levers are never scattered randomly: they are always pressed against a wall
    between LEVER_MIN_DOOR_DISTANCE and LEVER_MAX_DOOR_DISTANCE squares of the
    door they open, so players find the mechanism right beside the gate. The
    search is deterministic - the closest wall tile to the door wins, with
    stable tie breaks - so the same room always yields the same lever tile.
    """
    door_x, door_y = door_position
    height = len(bitmap)
    width = len(bitmap[0])
    solid = set(solid_wall_tiles) if solid_wall_tiles else set()

    def is_wall(tile_x: int, tile_y: int) -> bool:
        return (
            0 <= tile_x < width
            and 0 <= tile_y < height
            and (bitmap[tile_y][tile_x] == "#" or (tile_x, tile_y) in solid)
        )

    def lever_rank(tile: Tuple[int, int]) -> Tuple[int, int, int, int, int]:
        """Closer to the door first, then hugging the door's own wall, then stable."""
        tile_x, tile_y = tile
        offset_x = abs(tile_x - door_x)
        offset_y = abs(tile_y - door_y)
        shares_door_row_or_column = 0 if offset_x == 0 or offset_y == 0 else 1
        wall_neighbours = sum(
            is_wall(neighbor_x, neighbor_y)
            for neighbor_x, neighbor_y in (
                (tile_x - 1, tile_y),
                (tile_x + 1, tile_y),
                (tile_x, tile_y - 1),
                (tile_x, tile_y + 1),
            )
        )
        return (
            offset_x + offset_y,
            shares_door_row_or_column,
            -wall_neighbours,
            tile_y,
            tile_x,
        )

    candidates = [
        tile
        for tile in floor_tiles
        if bitmap[tile[1]][tile[0]] == "."
        and LEVER_MIN_DOOR_DISTANCE
        <= abs(tile[0] - door_x) + abs(tile[1] - door_y)
        <= LEVER_MAX_DOOR_DISTANCE
        and any(
            is_wall(neighbor_x, neighbor_y)
            for neighbor_x, neighbor_y in (
                (tile[0] - 1, tile[1]),
                (tile[0] + 1, tile[1]),
                (tile[0], tile[1] - 1),
                (tile[0], tile[1] + 1),
            )
        )
    ]
    if not candidates:
        return None
    return min(candidates, key=lever_rank)


def _generate_rest_area_bitmap(room: RoomNode) -> List[str]:
    width, height = 40, 20
    divider_x = width // 2
    bitmap = [["#" for _ in range(width)] for _ in range(height)]
    for tile_y in range(1, height - 1):
        for tile_x in range(1, width - 1):
            bitmap[tile_y][tile_x] = "."
        bitmap[tile_y][divider_x] = "#"

    gate_tiles = [(divider_x, tile_y) for tile_y in range(7, 12)]
    gate_door = gate_tiles[len(gate_tiles) // 2]
    bitmap[gate_door[1]][gate_door[0]] = "D"
    # The lever belongs on the divider wall beside the gate, not out in the open room.
    lever = _select_lever_tile(
        bitmap,
        [(tile_x, tile_y) for tile_y in range(1, height - 1) for tile_x in range(1, divider_x)],
        gate_door,
        solid_wall_tiles=set(gate_tiles),
    )
    if lever is None:
        raise ValueError(f"Rest area {room.room_id} has no wall tile beside its gate for a lever")
    bitmap[lever[1]][lever[0]] = "V"

    def spread_rows(count: int) -> List[int]:
        return [round(2 + index * (height - 5) / (count + 1)) for index in range(1, count + 1)]

    room.stair_destinations = {}
    for destination, tile_y in zip(room.connected_from, spread_rows(len(room.connected_from))):
        position = (3, tile_y)
        bitmap[position[1]][position[0]] = "^"
        room.stair_destinations[position] = destination
    for destination, tile_y in zip(room.connected_to, spread_rows(len(room.connected_to))):
        position = (width - 4, tile_y)
        bitmap[position[1]][position[0]] = "v"
        room.stair_destinations[position] = destination

    locked_tiles = sum(
        bitmap[tile_y][tile_x] != "#"
        for tile_y in range(1, height - 1)
        for tile_x in range(divider_x + 1, width - 1)
    )
    room.gates = {
        "G1": {
            "tiles": gate_tiles,
            "door": gate_door,
            "lever": lever,
            "locked_tiles": locked_tiles,
        }
    }
    room.gathering_nodes = {}
    room.monster_spawn_points = []
    return ["".join(row) for row in bitmap]


def _generate_room_bitmap(room: RoomNode, rng: random.Random, spawn_point_ratio: float) -> List[str]:
    if room.is_resting_area:
        return _generate_rest_area_bitmap(room)

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

    # A room can end up with no stairs at all (no connections on either side), in
    # which case there is no seed tile to flood fill from.
    if room.stair_destinations:
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

    if room.stair_destinations:
        _connect_walkable_areas(
            bitmap,
            {next(iter(room.stair_destinations))},
            door_walls,
            door_tiles,
            doorways,
            rng,
        )

    room.gates = _place_gates(bitmap, room_floor_tiles, doorways, room.stair_destinations, rng)
    # room.bitmap is only bound by the caller once this function returns, so publish
    # the working grid now for the closet pass that reads and edits it.
    room.bitmap = bitmap
    _seal_random_stair_closets(room, rng)

    def place_tile(tile: str, count: int) -> List[Tuple[int, int]]:
        candidates = [
            (tile_x, tile_y)
            for tile_x, tile_y in room_floor_tiles
            if bitmap[tile_y][tile_x] == "."
        ]
        placed = []
        for _ in range(min(count, len(candidates))):
            tile_x, tile_y = rng.choice(candidates)
            bitmap[tile_y][tile_x] = tile
            candidates.remove((tile_x, tile_y))
            placed.append((tile_x, tile_y))
        return placed

    area_scale = min(4, 1 + width * height // 2200)
    room.gathering_nodes = {}
    for position in place_tile("G", rng.randint(1, area_scale)):
        room.gathering_nodes[position] = {
            "material": rng.choice(("Stone", "Ore", "Herbs", "Timber")),
            "amount": rng.randint(1, 3),
        }
    chest_count = rng.choices((0, 1, 2), weights=(6, 3, 1) if room.is_dead_end else (7, 3, 1))[0]
    for _ in range(chest_count):
        place_tile("C", 1)

    lore_count = 1 if room.is_lore_room or room.is_dead_end or rng.random() < 0.3 else 0
    place_tile("L", lore_count)

    floor_tile_count = sum(tile not in ("#", "D") for row in bitmap for tile in row)
    spawn_point_count = (
        0
        if room.is_resting_area or floor_tile_count < MIN_SPAWN_ROOM_TILES
        else ceil(floor_tile_count * spawn_point_ratio)
    )
    room.monster_spawn_points = _place_monster_spawn_points(
        bitmap,
        spawn_point_count,
        door_tiles,
        room.stair_destinations,
        room.gates,
        rng,
    )

    return ["".join(row) for row in bitmap]


def _place_monster_spawn_points(
    bitmap: List[List[str]],
    count: int,
    door_tiles: set[Tuple[int, int]],
    stair_destinations: Dict[Tuple[int, int], str],
    gates: Dict[str, Dict[str, object]],
    rng: random.Random,
) -> List[Tuple[int, int]]:
    height = len(bitmap)
    width = len(bitmap[0])
    reserved = set(door_tiles) | set(stair_destinations)
    for gate in gates.values():
        reserved.update(gate["tiles"])
        reserved.add(gate["door"])
        reserved.add(gate["lever"])

    walkable_tiles = {".", "C", "G", "L", "^", "v", "V"}
    candidates = [
        (tile_x, tile_y)
        for tile_y in range(1, height - 1)
        for tile_x in range(1, width - 1)
        if bitmap[tile_y][tile_x] == "#"
        and any(
            bitmap[neighbor_y][neighbor_x] in walkable_tiles
            for neighbor_x, neighbor_y in (
                (tile_x - 1, tile_y),
                (tile_x + 1, tile_y),
                (tile_x, tile_y - 1),
                (tile_x, tile_y + 1),
            )
        )
        and all(max(abs(tile_x - reserved_x), abs(tile_y - reserved_y)) > 2 for reserved_x, reserved_y in reserved)
    ]

    selected = []
    while candidates and len(selected) < count:
        if not selected:
            position = rng.choice(candidates)
        else:
            distances = {
                position: min(
                    abs(position[0] - placed_x) + abs(position[1] - placed_y)
                    for placed_x, placed_y in selected
                )
                for position in candidates
            }
            greatest_distance = max(distances.values())
            farthest_candidates = [position for position, distance in distances.items() if distance == greatest_distance]
            position = rng.choice(farthest_candidates)
        selected.append(position)
        candidates.remove(position)
        bitmap[position[1]][position[0]] = "M"

    return selected


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

            door_position = min(
                doorway_tiles,
                key=lambda point: sum(
                    max(abs(point[0] - other_x), abs(point[1] - other_y))
                    for other_x, other_y in doorway_tiles
                ),
            )
            # The lever must sit on the player side of the gate, against a wall,
            # 2-4 squares from the door it opens.
            lever_position = _select_lever_tile(
                bitmap,
                [point for point in room_floor_tiles if point in after_closing],
                door_position,
                solid_wall_tiles=set(doorway_tiles),
            )
            if lever_position is None:
                continue
            candidates.append((len(locked_section), doorway, doorway_tiles, door_position, locked_section, lever_position))

        if not candidates:
            break

        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        preferred = candidates[:min(3, len(candidates))]
        weights = [candidate[0] for candidate in preferred]
        locked_count, doorway, doorway_tiles, door_position, locked_section, lever_position = rng.choices(
            preferred, weights=weights, k=1
        )[0]
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
